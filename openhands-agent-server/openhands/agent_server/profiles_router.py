"""HTTP 端点用于管理命名的 LLM 配置（配置文件）。"""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request, status
from pydantic import BaseModel, Field, SecretStr

from openhands.agent_server._secrets_exposure import (
    build_expose_context,
    decrypt_incoming_llm_secrets,
    get_cipher,
    get_config,
    parse_expose_secrets_header,
    store_errors,
    translate_missing_cipher,
)
from openhands.agent_server.persistence import (
    PersistedSettings,
    get_agent_profile_store,
    get_llm_profile_store,
    get_provider_connections_store,
    get_settings_store,
)
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.llm.exceptions import (
    LLMError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
    is_quota_exhaustion_error,
)
from openhands.sdk.llm.llm_profile_store import (
    PROFILE_NAME_PATTERN,
    ProfileLimitExceeded,
    canonical_profile_name,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.profiles import (
    ProfileReferenced,
    delete_llm_profile,
    rename_llm_profile,
)
from openhands.sdk.settings import OpenHandsAgentSettings
from openhands.sdk.utils.redact import redact_text_secrets


logger = get_logger(__name__)

profiles_router = APIRouter(prefix="/profiles", tags=["Profiles"])

MAX_PROFILES = 50

ProfileName = Annotated[
    str,
    Path(min_length=1, max_length=64, pattern=PROFILE_NAME_PATTERN),
]


class ProfileInfo(BaseModel):
    name: str
    model: str | None = None
    base_url: str | None = None
    provider_connection_id: str | None = None
    provider_connection_broken: bool = False
    api_key_set: bool = False


class ProfileListResponse(BaseModel):
    profiles: list[ProfileInfo]
    active_profile: str | None = None


class ProfileDetailResponse(BaseModel):
    """除非通过 X-Expose-机密明确请求，否则机密为空。"""

    name: str
    config: dict[str, Any]
    api_key_set: bool = False


class ProfileMutationResponse(BaseModel):
    name: str
    message: str


class SaveProfileRequest(BaseModel):
    llm: LLM
    include_secrets: bool = Field(
        default=True,
        description="Whether to persist the API key with the profile.",
    )


class RenameProfileRequest(BaseModel):
    new_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=PROFILE_NAME_PATTERN,
    )


def _has_api_key(llm: LLM) -> bool:
    if not isinstance(llm.api_key, SecretStr):
        return False
    return bool(llm.api_key.get_secret_value().strip())


def _profile_api_key_set(request: Request, llm: LLM) -> bool:
    """有效的密钥存在：配置文件自己的密钥或其提供商的密钥。

    链接到提供商连接的配置文件不携带内联密钥（保存时清除），因此其密钥存在于连接上。
    """
    if _has_api_key(llm):
        return True
    connection_id = llm.provider_connection_id
    if not connection_id:
        return False
    config = get_config(request)
    cipher = get_cipher(request)
    # 提供程序存储读取可能会引发损坏的文件； 映射它而不是让它作为未处理的 500 出现在 GET
    #  /profiles/{name}. 上
    #
    with store_errors():
        connection = get_provider_connections_store(config).get(
            connection_id, cipher=cipher
        )
    return connection is not None and connection.api_key_value() is not None


def _set_active_profile_if_matches(
    request: Request, old_name: str, new_name: str | None
) -> bool:
    config = get_config(request)
    settings_store = get_settings_store(config)
    settings = settings_store.load() or PersistedSettings()
    active = settings.active_profile
    # ``foo.json`` 寻址存储中的配置文件 ``foo``，因此比较存储密钥。
    if active is None or canonical_profile_name(active) != canonical_profile_name(
        old_name
    ):
        return False

    def update_active(settings: PersistedSettings) -> PersistedSettings:
        settings.active_profile = (
            canonical_profile_name(new_name) if new_name is not None else None
        )
        return settings

    settings_store.update(update_active)
    return True


@profiles_router.get("", response_model=ProfileListResponse)
def list_profiles(request: Request) -> ProfileListResponse:
    """列出所有已保存的 LLM 个配置文件。

    返回配置文件列表以及当前活动的配置文件名称（如果已激活）。 active_profile 跟踪当
    前正在使用的 LLM 配置文件配置。
    """
    config = get_config(request)
    settings_store = get_settings_store(config)
    settings = settings_store.load() or PersistedSettings()

    store = get_llm_profile_store()
    with store_errors():
        summaries = store.list_summaries()

    return ProfileListResponse(
        profiles=[ProfileInfo(**s) for s in summaries],
        active_profile=settings.active_profile,
    )


@profiles_router.get("/{name}", response_model=ProfileDetailResponse)
def get_profile(request: Request, name: ProfileName) -> ProfileDetailResponse:
    """获取配置文件的配置。

    使用 ``X-Expose-Secrets`` 标头控制机密曝光：
    - ``encrypted``：返回密码加密值（对于前端客户端来说是安全的）
    - ``plaintext``：解析链接的提供程序并为构建可运行的 LLM 配置的后端客户端返回原始
    机密值
    - （不存在）：返回带有 ``api_key_set`` 指示符的空 ``api_key``
    """
    expose_mode = parse_expose_secrets_header(request)
    cipher = get_cipher(request)

    store = get_llm_profile_store()
    try:
        with store_errors():
            # 运行时读取需要当前提供程序凭据。 编辑器读取保留存储的引用，包括悬空引用。
            #
            llm = store.load(
                name, cipher=cipher, resolve_provider=expose_mode == "plaintext"
            )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{name}' not found",
        )

    if expose_mode:
        context = build_expose_context(expose_mode, cipher)
        with translate_missing_cipher():
            config: dict[str, Any] = llm.model_dump(mode="json", context=context)
    else:
        config = llm.model_dump(mode="json")
        config["api_key"] = None

    return ProfileDetailResponse(
        name=name, config=config, api_key_set=_profile_api_key_set(request, llm)
    )


@profiles_router.post(
    "/{name}",
    response_model=ProfileMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_profile(
    request: Request,
    name: ProfileName,
    body: SaveProfileRequest,
) -> ProfileMutationResponse:
    """将 LLM 配置保存为命名配置文件。

    覆盖同名的现有配置文件。 如果创建新配置文件超出 ``MAX_PROFILES``，则返回 409。

    当配置``OH_SECRET_KEY``时，机密在REST处加密。 客户端可以提交密码加密的机密，该密
    码将在使用存储密码重新加密之前在服务器端解密。
    """
    cipher = get_cipher(request)
    llm = decrypt_incoming_llm_secrets(body.llm, cipher) if cipher else body.llm
    store = get_llm_profile_store()
    try:
        with store_errors():
            store.save(
                name,
                llm,
                include_secrets=body.include_secrets,
                cipher=cipher,
                max_profiles=MAX_PROFILES,
            )
    except ProfileLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Profile limit reached ({MAX_PROFILES}). "
                "Delete a profile before saving a new one."
            ),
        )

    logger.info(f"Saved profile '{name}' (include_secrets={body.include_secrets})")
    return ProfileMutationResponse(name=name, message=f"Profile '{name}' saved")


class ValidateProfileRequest(BaseModel):
    """LLM 飞行前验证的请求正文。

    接受一个 LLM 配置(相同的形状 ``SaveProfileRequest.llm``）因此前端可以验证草稿 *之
    前* 坚持它。
    """

    llm: LLM


class ValidateProfileError(BaseModel):
    """验证失败时返回结构化错误。"""

    type: str
    message: str


class ValidateProfileResponse(BaseModel):
    """LLM 飞行前检查的结果。"""

    valid: bool
    error: ValidateProfileError | None = None


# 应不阻止保存的错误 — 它们是暂时的，与配置本身的正确性无关。
#
_TRANSIENT_ERROR_TYPES = (LLMRateLimitError, LLMTimeoutError)

# 单次飞行前尝试的上限（以秒为单位）。 个人资料自己的
# ``timeout``（默认300秒）和重试策略用于真实对话； 验证答案在此范围内。
#
PREFLIGHT_TIMEOUT_SECONDS = 15


def _preflight_llm(llm: LLM) -> LLM:
    """复制 ``llm`` 以对配置的模型进行一次有限尝试。

    没有重试，一个短超时，以及没有回退方案 LLMs（每个都会带来自己的重试政策，一个工作
    回退方案会隐藏一个损坏的主）。
    """
    timeout = PREFLIGHT_TIMEOUT_SECONDS
    if llm.timeout is not None:
        timeout = min(llm.timeout, timeout)
    return llm.model_copy(
        update={"num_retries": 0, "timeout": timeout, "fallback_strategy": None}
    )


def _invalid(name: str, exc: LLMError) -> ValidateProfileResponse:
    error_type = type(exc).__name__
    safe_msg = redact_text_secrets(exc.message)
    logger.info(f"Profile '{name}' pre-flight failed: {error_type}: {safe_msg}")
    return ValidateProfileResponse(
        valid=False,
        error=ValidateProfileError(type=error_type, message=safe_msg),
    )


@profiles_router.post(
    "/{name}/validate",
    response_model=ValidateProfileResponse,
)
async def validate_profile(
    request: Request,
    name: ProfileName,
    body: ValidateProfileRequest,
) -> ValidateProfileResponse:
    """飞行前检查：触发最小 LLM 完成以捕获错误配置。

    实例化提交的 LLM 配置并发送了 1-token 完成表面错误，如无效的模型名称、缺失的提供
    者前缀、坏的基类 URLs, and invalid API keys
     — *之前* 该资料已保存。

    ping 是一次以 ``PREFLIGHT_TIMEOUT_SECONDS``（或更短的配置 ``timeout``）为界的尝试
    ； 未使用配置的重试策略，因此无法访
    问的端点立即应答。

    超时临时错误（速率限制等）被视为非阻塞：响应 ``valid=True``，没有错误，因为这些错
    误并不表明配置错误。 报告预算或配额耗尽的 429 不是暂时的并且会
    失败验证。
    """
    cipher = get_cipher(request)
    llm = decrypt_incoming_llm_secrets(body.llm, cipher) if cipher else body.llm
    # 检查链接到提供者连接的草稿与连接的凭据，作为激活和 ``switch_llm`` 运行它。 无操作
    # 无
    # ``provider_connection_id``; 悬空链接是 422 命名它。
    with store_errors():
        llm = get_llm_profile_store().resolve_provider_connection(llm, cipher=cipher)

    messages = [
        Message(
            role="system",
            content=[TextContent(text="Reply with one token.")],
        ),
        Message(
            role="user",
            content=[TextContent(text="ping")],
        ),
    ]

    try:
        # 恢复运行时订阅凭据、镜像 ``from_persisted``。 前端发送 auth_type="subscription
        # " 但 OAuth 访问令牌位于凭据存储中，而不是已序列化 LLM 配置中。 如果没有这个，
        # 飞行前会发送 api_key=None 并失败，并显示“提供的 API 密钥不正确：None”。
        #
        # 在事件循环之外并在处理的路径内运行同步工厂（可能会执行网络 token 刷新），因此
        # 凭据错误显示为 ``valid=False`` 而不是 500。
        #
        if getattr(llm, "auth_type", None) == "subscription":
            from openhands.sdk.llm.auth.openai import (
                create_subscription_llm_from_config,
            )

            llm = await asyncio.to_thread(create_subscription_llm_from_config, llm)

        llm = _preflight_llm(llm)
        # 镜像运行时分派（参见 ``LLM.agenerate``）并保持异步，以便提供程序 I/O 不会固定
        # FastAPI 事件循环。
        #
        if llm.uses_responses_api():
            await llm.aresponses(messages=messages, max_tokens=1)
        else:
            await llm.acompletion(messages=messages, max_tokens=1)
    except _TRANSIENT_ERROR_TYPES as exc:
        if is_quota_exhaustion_error(exc):
            return _invalid(name, exc)
        # 瞬态——不阻止保存
        logger.info(
            f"Profile '{name}' pre-flight hit a transient error "
            f"({type(exc).__name__}); not blocking save."
        )
        return ValidateProfileResponse(valid=True)
    except (
        # LLMServiceUnavailableError（提供程序 503）被故意视为阻塞配置错误：在这一层，提
        # 供程序中断与错误的基础 URL 无法区分，因此我们更喜欢 False 否定而不是默默地保存
        # 错误配置的配置文件。
        #
        LLMServiceUnavailableError,
        LLMError,
    ) as exc:
        return _invalid(name, exc)
    except Exception as exc:
        # 未知错误 - 阻止保存并显示原始消息，以便用户可以调试，但可以进行一般分类。
        #
        msg = redact_text_secrets(str(exc) or type(exc).__name__)
        logger.info(f"Profile '{name}' pre-flight failed (unknown): {msg}")
        return ValidateProfileResponse(
            valid=False,
            error=ValidateProfileError(
                type=type(exc).__name__,
                message=msg,
            ),
        )

    return ValidateProfileResponse(valid=True)


@profiles_router.delete("/{name}", response_model=ProfileMutationResponse)
def delete_profile(request: Request, name: ProfileName) -> ProfileMutationResponse:
    """删除已保存的配置文件（幂等）。

    由智能体-profile FK 保护：返回 409 命名引用者（如果有）
    ``AgentProfile`` 仍然通过 ``llm_profile_ref`` 引用此 LLM 简介。
    """
    store = get_llm_profile_store()
    agent_store = get_agent_profile_store()
    try:
        with store_errors():
            delete_llm_profile(agent_store, store, name)
    except ProfileReferenced as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if _set_active_profile_if_matches(request, name, None):
        logger.info(f"Cleared active_profile for deleted profile '{name}'")
    logger.info(f"Deleted profile '{name}'")
    return ProfileMutationResponse(name=name, message=f"Profile '{name}' deleted")


@profiles_router.post("/{name}/rename", response_model=ProfileMutationResponse)
def rename_profile(
    request: Request,
    name: ProfileName,
    body: RenameProfileRequest,
) -> ProfileMutationResponse:
    """自动重命名已保存的配置文件。

    如果源不存在，则返回 404；如果 ``new_name`` 已存在，则返回 409。 同名重命名是经过
    验证的无操作（如果丢失，仍然是 404）。

    如果重命名的配置文件是当前活动的配置文件，active_profile 设置将更新为新名称。 任
    何引用旧名称的
    ``AgentProfile.llm_profile_ref`` 都会在锁步骤中级联到新名称。
    """
    store = get_llm_profile_store()
    agent_store = get_agent_profile_store()
    try:
        with store_errors():
            rename_llm_profile(agent_store, store, name, body.new_name)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{name}' not found",
        )
    except FileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile '{body.new_name}' already exists",
        )

    if name != body.new_name and _set_active_profile_if_matches(
        request, name, body.new_name
    ):
        logger.info(f"Updated active_profile from '{name}' to '{body.new_name}'")

    if name == body.new_name:
        message = f"Profile '{name}' unchanged (same name)"
    else:
        message = f"Profile '{name}' renamed to '{body.new_name}'"
    logger.info(message)
    return ProfileMutationResponse(name=body.new_name, message=message)


class ActivateProfileResponse(BaseModel):
    """配置文件激活的响应模型。"""

    name: str
    message: str
    llm_applied: bool = True


@profiles_router.post("/{name}/activate", response_model=ActivateProfileResponse)
def activate_profile(request: Request, name: ProfileName) -> ActivateProfileResponse:
    """激活已保存的 LLM 配置文件。

    这个端点：
    1. 加载指定配置文件的 LLM 配置
    2. 将其应用于当前的 OpenHands 智能体设置（更新
       ``agent_settings.llm``); ACP 设置没有 LLM 需要更新
    3. 将配置文件名称记录为前端跟踪的活动配置文件

    如果配置文件不存在，则返回 404。

    使用 ``GET /api/profiles`` 查看哪个角色是当前激活的，通过 ``active_profile`` 字段
    。
    """
    cipher = get_cipher(request)
    config = get_config(request)

    # 加载配置文件。 ``load`` 解析任何引用的提供者连接（使用时读取），因此应用于设置的
    # LLM 已经携带共享的 api_key / base_url； ``provider_connection_id`` 被保留，以便稍
    # 后的轮换在下一次激活或启动时重新解析。
    #
    profile_store = get_llm_profile_store()
    # 悬空的 provider_connection_id 引发 ProviderConnectionNotFound，其中 store_errors()
    #  映射到 422。
    #
    try:
        with store_errors():
            llm = profile_store.load(name, cipher=cipher)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{name}' not found",
        )

    settings_store = get_settings_store(config)
    llm_applied = False

    def apply_profile(settings: PersistedSettings) -> PersistedSettings:
        nonlocal llm_applied
        if isinstance(settings.agent_settings, OpenHandsAgentSettings):
            settings.agent_settings = settings.agent_settings.model_copy(
                update={"llm": llm}
            )
            llm_applied = True
        settings.active_profile = canonical_profile_name(name)
        return settings

    try:
        settings_store.update(apply_profile)
    except (OSError, PermissionError):
        logger.error("Failed to activate profile - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to activate profile")
    except RuntimeError as e:
        logger.error(f"Failed to activate profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Settings file is corrupted or encrypted with a different key: "
                "restore that key as OH_SECRET_KEY or add it to "
                "OH_PREVIOUS_SECRET_KEYS"
            ),
        )

    logger.info(f"Activated profile '{name}'")
    return ActivateProfileResponse(
        name=name,
        message=(
            f"Profile '{name}' activated and applied to current settings"
            if llm_applied
            else f"Profile '{name}' activated"
        ),
        llm_applied=llm_applied,
    )
