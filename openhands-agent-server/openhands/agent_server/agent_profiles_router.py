"""HTTP 端点用于管理命名的 ``AgentProfile`` 启动规范。

镜像 ``profiles_router.py``（LLM ``/api/profiles`` 路由器），但服务于引用承载：class:
`~openhands.sdk.profiles.AgentProfile` 联合并保留
*单独的*活动指针（``active_agent_profile_id``）。 这里的激活是
仅指针 - 与 LLM ``/activate`` 不同，它必须 ** 不 ** 写入
``agent_settings``（仅限创建时间的合约）。

``POST /{name}/materialize`` 对存储的配置文件或草稿正文执行试运行解析，并返回
:class:`~openhands.sdk.profiles.AgentProfileDiagnostics` （永远不会在
悬空引用——那些出现在正文中的引用）。
"""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field, PlainValidator, ValidationError

from openhands.agent_server._secrets_exposure import (
    get_cipher,
    get_config,
    store_errors,
)
from openhands.agent_server.config import Config
from openhands.agent_server.launch import (
    can_probe_tools,
    server_launch_stores,
    target_launch_runtime,
)
from openhands.agent_server.persistence import (
    PersistedSettings,
    get_agent_profile_store,
    get_llm_profile_store,
    get_settings_store,
)
from openhands.agent_server.profiles_router import MAX_PROFILES, _has_api_key
from openhands.sdk.launch import preview_launch
from openhands.sdk.llm import LLM
from openhands.sdk.llm.llm_profile_store import (
    ProfileLimitExceeded as LLMProfileLimitExceeded,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.profiles import (
    SEED_PROFILE_NAME,
    ACPAgentProfile,
    AgentProfile,
    AgentProfileDiagnostics,
    AgentProfileInfo,
    AgentProfileListResponse,
    AgentProfileStore,
    OpenHandsAgentProfile,
    ProfileLimitExceeded,
    build_seed_profile,
    safe_validation_error_detail,
    save_profile_preserving_identity,
    validate_agent_profile,
)
from openhands.sdk.profiles.agent_profile_store import (
    PROFILE_NAME_PATTERN,
    canonical_profile_name,
)
from openhands.sdk.settings.model import OpenHandsAgentSettings
from openhands.sdk.utils.cipher import Cipher


logger = get_logger(__name__)

agent_profiles_router = APIRouter(prefix="/agent-profiles", tags=["Agent Profiles"])

MAX_AGENT_PROFILES = 50

ProfileName = Annotated[
    str,
    Path(min_length=1, max_length=64, pattern=PROFILE_NAME_PATTERN),
]
ProfileId = Annotated[str, Path(min_length=1, max_length=128)]


class AgentProfileDetailResponse(BaseModel):
    name: str
    profile: dict[str, Any]


class AgentProfileMutationResponse(BaseModel):
    name: str
    message: str


class ActivateAgentProfileResponse(BaseModel):
    id: str
    message: str
    # 始终False：通过合约仅激活指针。 现场记录表明 agent_settings 未受影响； Materialize
    #  (#3717) 是将配置文件解析为设置的路径。
    #
    agent_settings_applied: bool = False


def _raw_profile_payload(value: Any) -> dict[str, Any] | None:
    if value is not None and not isinstance(value, dict):
        raise ValueError("profile must be an object")
    return value


class MaterializeAgentProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 保持原始状态，因此选秀会经历与保存相同的迁移。
    profile: Annotated[
        dict[str, Any] | None,
        PlainValidator(
            _raw_profile_payload, json_schema_input_type=AgentProfile | None
        ),
    ] = Field(
        default=None,
        description=(
            "Draft profile to evaluate instead of the stored one. The path name "
            "overrides the draft's name."
        ),
    )


class RenameAgentProfileRequest(BaseModel):
    new_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=PROFILE_NAME_PATTERN,
    )


def _llm_has_real_config(llm: LLM) -> bool:
    """True 当 ``llm`` 携带真实的、用户提供的配置时。

    区分已经工作的设置——一个真实的API密钥、订阅认证或一个自定义端点——与未配置账户上的
    裸SDK字段默认值（``model="gpt-5.5"``，没有
    ``api_key``）。 只有前者值得镜像到命名的 ``default`` LLM 配置文件中； 坚持后者会
    留下一个无密钥、无功能的“幽灵”配置文件，用户从未要求
    过该配置文件，也没有任何东西可以清理它（#4031）。
    """
    if _has_api_key(llm):
        return True
    if llm.is_subscription or llm.auth_type == "subscription":
        return True
    if llm.base_url and llm.base_url.strip():
        return True
    return False


def _seed_default_llm_profile(llm: LLM, cipher: Cipher | None) -> str:
    """将实时 LLM 配置镜像到 ``SEED_PROFILE_NAME`` LLM 配置文件中。

    ``build_seed_profile`` 回退到原始名称 ``SEED_PROFILE_NAME`` when no LLM 该记录是
    活跃的，假设有一个名为该记
    录的记录存在——但从未创建过，所以种子的智能体 profile's
    ``llm_profile_ref`` 从出生起就悬挂着（#3933）。 镜像云
    ``SaasSettingsStore``的遗产-LLM回填：具体化当前
    ``agent_settings.llm`` 在该名称下，以便解析引用，除非配置文件已存储在那里（切勿破
    坏它）。

    Only a *真实的，已存在的*  LLM 配置是已持久化 (``_llm_has_real_config`` — an API
    密钥、订阅认证，或自定义
    base_url），这正是回填存在的遗留/云迁移场景。 在一台全新的、未配置的账户上， LLM
    untouched SDK 默认值（无密钥）
    ``gpt-5.5``); 持久化*那个*只会在配置文件列表中散布无密钥、不可用的``default``“幽
    灵”配置文件（＃4031），因此我们跳过保存并离开
    ``llm_profile_ref="default"`` 作为软/悬垂引用 —— 已配置的画布 "LLM 未配置" 标志和
    可读的启动时间错误已经覆盖了该状态，而不
    是报告：``valid`` False
    ``llm_profile_resolved`` False 和 ``errors`` 条目
    ``"LLM profile 'default' not found"``.

    ``load()`` 通过检查存在性，而不是 ``list()``：存储库直接将名称解析为文件系统路径
    ，因此在不区分大小写的文件系统 (macOS/Windows)
     中，一个不同大小写的 ``Default`` 配置已经占据了 ``default`` 路径，尽管它在不区分
     大小写的情况下不会匹配
    ``list()`` 成员资格检查 - 否则这种不匹配会让 ``save()`` 默默地破坏它。
    """
    llm_store = get_llm_profile_store()
    with store_errors():
        try:
            llm_store.load(SEED_PROFILE_NAME, cipher=cipher)
            return SEED_PROFILE_NAME
        except FileNotFoundError:
            pass
        except ValueError:
            # 名称已被某些内容占用 (e.g. 损坏/无法解析的文件）——切勿覆盖它； 相反，在实
            # 现/启动时会出现损坏的参考表面。
            #
            logger.warning(
                f"Default LLM profile '{SEED_PROFILE_NAME}' exists but "
                "failed to load; leaving it as-is"
            )
            return SEED_PROFILE_NAME
        if not _llm_has_real_config(llm):
            # 从未配置的帐户：不要持久化无密钥幽灵配置文件。 让裁判柔软/悬空； 横幅+启动
            # 时错误会处理它，并且一旦用户保存配置文件，它就会真正解决。
            #
            logger.info(
                f"Skipping default LLM profile '{SEED_PROFILE_NAME}' seed: "
                "no real LLM config yet (leaving llm_profile_ref as a soft ref)"
            )
            return SEED_PROFILE_NAME
        try:
            llm_store.save(
                SEED_PROFILE_NAME,
                llm,
                include_secrets=True,
                cipher=cipher,
                max_profiles=MAX_PROFILES,
            )
            logger.info(f"Seeded default LLM profile '{SEED_PROFILE_NAME}'")
        except LLMProfileLimitExceeded:
            # 无法将实时 LLM 镜像为个人资料； 智能体配置文件的 llm_profile_ref 仍然会悬
            # 空，但不会比以前更糟糕。
            #
            logger.warning(
                "Could not seed default LLM profile "
                f"'{SEED_PROFILE_NAME}': profile limit reached"
            )
    return SEED_PROFILE_NAME


def _ensure_active_profile(
    store: AgentProfileStore, config: Config, cipher: Cipher | None
) -> None:
    """将 ``active_agent_profile_id`` 保留在已存储的配置文件上。

    丢失或悬空的指针会移动到 ``default``，当不存在时，该指针会从当前的
    ``agent_settings`` 播种，因此每次启动都有一个配置文件。 当
    ``default`` 不可读或存储太满而无法播种，而是激活第一个其他配置文件。 锁跨越检查、
    种子和指针写入，因此并发调用者种子一次并就指针达成一致。
    """
    settings_store = get_settings_store(config)
    with store_errors(), store.lock():
        settings = settings_store.load() or PersistedSettings()
        active_id = settings.active_agent_profile_id
        if active_id is not None and store.name_for_id(active_id) is not None:
            return
        target = _profile_to_activate(store, settings, cipher)
        if target is None:
            return
        name, profile_id = target

        def set_pointer(s: PersistedSettings) -> PersistedSettings:
            s.active_agent_profile_id = profile_id
            return s

        settings_store.update(set_pointer)
        logger.info(f"Activated agent profile '{name}' (id={profile_id})")


def _profile_to_activate(
    store: AgentProfileStore, settings: PersistedSettings, cipher: Cipher | None
) -> tuple[str, str] | None:
    """返回 ``default`` 的名称和 id，如果商店有空间，则为其播种。"""
    try:
        profile = store.load(SEED_PROFILE_NAME)
        return profile.name, str(profile.id)
    except FileNotFoundError:
        try:
            profile = _seed_default_profile(store, settings, cipher)
            return profile.name, str(profile.id)
        except ProfileLimitExceeded:
            pass
    except ValueError:
        logger.warning(
            f"Agent profile '{SEED_PROFILE_NAME}' exists but failed to load; "
            "leaving it as-is"
        )
    first = next(
        (
            s
            for s in store.list_summaries()
            if s["id"] and s["name"] != SEED_PROFILE_NAME
        ),
        None,
    )
    return (first["name"], str(first["id"])) if first else None


def _seed_default_profile(
    store: AgentProfileStore, settings: PersistedSettings, cipher: Cipher | None
) -> OpenHandsAgentProfile | ACPAgentProfile:
    active_llm_profile = settings.active_profile
    # 错误检查（不是 `is None`）：镜像 build_seed_profile 自己的
    # `active_llm_profile or SEED_PROFILE_NAME`  回退方案。 一个空格（e.g. 手编辑/遗留
    # settings.json, 或直接 PersistedSettings(active_profile="") construction — the HTTP
    #   PATCH  载荷'的模式验证器块为空，但存储的字段也没有这样的约束，所以回填必须在相同
    # 条件下触发，或者#3933悬垂引用才会再次出现。
    #
    if not active_llm_profile and settings.agent_settings.agent_kind != "acp":
        active_llm_profile = _seed_default_llm_profile(
            settings.agent_settings.llm, cipher
        )
    profile = build_seed_profile(settings.agent_settings, active_llm_profile)
    store.save(profile, max_profiles=MAX_AGENT_PROFILES)
    logger.info(f"Seeded default agent profile '{profile.name}' (id={profile.id})")
    return profile


def active_agent_profile(
    config: Config, cipher: Cipher | None
) -> OpenHandsAgentProfile | ACPAgentProfile | None:
    """返回活动的智能体配置文件，当 None 存在时激活 ``default``。"""
    store = get_agent_profile_store()
    _ensure_active_profile(store, config, cipher)
    settings = get_settings_store(config).load() or PersistedSettings()
    if settings.active_agent_profile_id is None:
        return None
    with store_errors():
        name = store.name_for_id(settings.active_agent_profile_id)
        if name is None:
            return None
        try:
            return store.load(name)
        except FileNotFoundError:
            return None


def _summary_id_for_name(store: AgentProfileStore, name: str) -> str | None:
    """返回存储在 ``name`` 下的配置文件的稳定 ID（如果存在）。"""
    name = canonical_profile_name(name)
    with store_errors():
        for summary in store.list_summaries():
            if summary.get("name") == name:
                sid = summary.get("id")
                return str(sid) if sid is not None else None
    return None


@agent_profiles_router.get("", response_model=AgentProfileListResponse)
def list_agent_profiles(request: Request) -> AgentProfileListResponse:
    """列出所有存储的智能体配置文件和活动指针。

    某些配置文件始终处于活动状态：在没有有效指针的情况下，``default`` 被激活，并且在
    不存在时从当前的 ``agent_settings`` 播种。
    """
    config = get_config(request)
    settings_store = get_settings_store(config)
    settings = settings_store.load() or PersistedSettings()

    store = get_agent_profile_store()
    _ensure_active_profile(store, config, get_cipher(request))
    settings = settings_store.load() or settings

    with store_errors():
        summaries = store.list_summaries()

    return AgentProfileListResponse(
        profiles=[AgentProfileInfo(**s) for s in summaries],
        active_agent_profile_id=settings.active_agent_profile_id,
    )


@agent_profiles_router.get("/{name}", response_model=AgentProfileDetailResponse)
def get_agent_profile(name: ProfileName) -> AgentProfileDetailResponse:
    """获取存储的配置文件。

    配置文件在 REST 处是机密自由的 (#4017)，因此没有任何内容可以屏蔽或公开 - 与 LLM
    ``/api/profiles`` 路由器不同，此端点没有
    ``X-Expose-Secrets`` 行为。
    """
    store = get_agent_profile_store()
    try:
        with store_errors():
            profile = store.load(name)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent profile '{name}' not found",
        )

    payload = profile.model_dump(mode="json")
    return AgentProfileDetailResponse(name=name, profile=payload)


def _validate_profile_payload(
    payload: dict[str, Any],
) -> OpenHandsAgentProfile | ACPAgentProfile:
    try:
        return validate_agent_profile(payload)
    except ValidationError as e:
        # 匹配 FastAPI 的请求 - 验证形状（``detail`` 是错误对象列表）：``loc``
        # /``type``/``msg``（``input`` 已删除 - 请参阅 safe_validation_error_detail 的文
        # 档字符串了解为什么 msg 现在是安全的）。
        #
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=safe_validation_error_detail(e),
        )
    except Exception:
        # 任何其他验证故障 (e.g. 架构/迁移错误）是客户端错误，而不是 500。 保持通用性——
        # 这些消息可以嵌入输入。
        #
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid agent profile",
        )


@agent_profiles_router.post(
    "/{name}",
    response_model=AgentProfileMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_agent_profile(
    name: ProfileName, body: dict[str, Any]
) -> AgentProfileMutationResponse:
    """将 ``AgentProfile`` 保存在 ``name`` 下（覆盖同名的）。

    路径 ``name`` 是权威的 - 它覆盖正文中的任何 ``name``。 该配置文件在 REST (#4017)
    处不受机密限制，因此不涉及密码/加密。 如果创
    建新的配置文件超出范围，则返回 409
    ``MAX_AGENT_PROFILES``.
    """
    profile = _validate_profile_payload({**body, "name": name})

    store = get_agent_profile_store()
    # id 由服务器管理（活动指针位于其上）：覆盖保留同名的 id 并修改版本； 创建一个新的
    # ID，忽略任何客户端提供的 ID。 ``save_profile_preserving_identity`` 通过读取 + 铸造
    #  + 保存保存存储锁，因此两个并发创建的相同新名称不能同时铸造 id 并互相破坏。
    #
    try:
        with store_errors():
            save_profile_preserving_identity(
                store, profile, max_profiles=MAX_AGENT_PROFILES
            )
    except ProfileLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Agent profile limit reached ({MAX_AGENT_PROFILES}). "
                "Delete a profile before saving a new one."
            ),
        )

    logger.info(f"Saved agent profile '{name}'")
    return AgentProfileMutationResponse(
        name=name, message=f"Agent profile '{name}' saved"
    )


@agent_profiles_router.delete("/{name}", response_model=AgentProfileMutationResponse)
def delete_agent_profile(
    request: Request, name: ProfileName
) -> AgentProfileMutationResponse:
    """删除存储的配置文件（幂等）。

    如果删除的配置文件是活动配置文件，则 ``default`` 变为活动状态，并从删除配置文件时
    的设置重新播种。 如果
    ``agent_settings``本身仍然处于非OpenHands变体中，首先将其重置为默认OpenHands 智能
    体设置，以避免ACP配置过期而影响其来源的配置
    文件。 服务器范围的``mcp_config``被结转。
    """
    store = get_agent_profile_store()
    deleted_id = _summary_id_for_name(store, name)

    with store_errors():
        store.delete(name)

    if deleted_id is not None:
        config = get_config(request)
        settings_store = get_settings_store(config)
        settings = settings_store.load() or PersistedSettings()
        if settings.active_agent_profile_id == deleted_id:

            def clear_pointer_and_reset_settings(
                s: PersistedSettings,
            ) -> PersistedSettings:
                s.active_agent_profile_id = None
                # 过时的非 OpenHands 设置比其个人资料的寿命更长。 重置为新的 OpenHands
                # 基础，而不是跨变体边界合并（参见 _apply_agent_settings_diff），除了
                # ``mcp_config``：它是服务器范围的 MCP 注册表每个其他配置文件解析
                # ``mcp_server_refs`` 状态，而不是 ACP 状态。
                #
                prior_kind = s.agent_settings.agent_kind
                if prior_kind != "openhands":
                    s.agent_settings = OpenHandsAgentSettings(
                        mcp_config=s.agent_settings.mcp_config
                    )
                    logger.info(
                        f"Reset agent_settings to default "
                        f"(agent_settings was agent_kind='{prior_kind}')"
                    )
                return s

            settings_store.update(clear_pointer_and_reset_settings)
            logger.info(f"Cleared active pointer for deleted profile '{name}'")
            _ensure_active_profile(store, config, get_cipher(request))

    logger.info(f"Deleted agent profile '{name}'")
    return AgentProfileMutationResponse(
        name=name, message=f"Agent profile '{name}' deleted"
    )


@agent_profiles_router.post(
    "/{name}/rename", response_model=AgentProfileMutationResponse
)
def rename_agent_profile(
    name: ProfileName, body: RenameAgentProfileRequest
) -> AgentProfileMutationResponse:
    """自动重命名存储的配置文件。

    稳定的 ``id`` 被保留，因此活动指针（以 ``id`` 为键）在重命名后保持不变。 如果源缺
    失则返回 404，如果源缺失则返回 409
    ``new_name`` 已被占用。
    """
    store = get_agent_profile_store()
    try:
        with store_errors():
            store.rename(name, body.new_name)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent profile '{name}' not found",
        )
    except FileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent profile '{body.new_name}' already exists",
        )

    if name == body.new_name:
        message = f"Agent profile '{name}' unchanged (same name)"
    else:
        message = f"Agent profile '{name}' renamed to '{body.new_name}'"
    logger.info(message)
    return AgentProfileMutationResponse(name=body.new_name, message=message)


@agent_profiles_router.post(
    "/{profile_id}/activate", response_model=ActivateAgentProfileResponse
)
def activate_agent_profile(
    request: Request, profile_id: ProfileId
) -> ActivateAgentProfileResponse:
    """通过稳定的 ``id`` 激活配置文件 — 仅指针。

    设置 ``active_agent_profile_id`` 而没有其他内容：与 LLM 不同
    ``/activate``，这**不**写``agent_settings``（仅限创建时间的合同）。 如果没有存储
    的配置文件具有该 ID，则返回 404。
    """
    store = get_agent_profile_store()
    with store_errors():
        known_ids = {
            str(s["id"]) for s in store.list_summaries() if s.get("id") is not None
        }
    if profile_id not in known_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent profile with id '{profile_id}' not found",
        )

    config = get_config(request)
    settings_store = get_settings_store(config)

    def set_pointer(settings: PersistedSettings) -> PersistedSettings:
        settings.active_agent_profile_id = profile_id
        return settings

    try:
        settings_store.update(set_pointer)
    except (OSError, PermissionError):
        logger.error("Failed to activate agent profile - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to activate agent profile")
    except RuntimeError as e:
        # 损坏/错误键入的设置文件是服务器端完整性故障，而不是客户端冲突。
        #
        logger.error(f"Failed to activate agent profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate agent profile",
        )

    logger.info(f"Activated agent profile id '{profile_id}'")
    return ActivateAgentProfileResponse(
        id=profile_id,
        message=f"Agent profile '{profile_id}' activated",
    )


@agent_profiles_router.post(
    "/{name}/materialize",
    response_model=AgentProfileDiagnostics,
)
async def materialize_agent_profile(
    request: Request,
    name: ProfileName,
    body: MaterializeAgentProfileRequest | None = None,
) -> AgentProfileDiagnostics:
    """预览配置文件的启动； 返回诊断报告。

    预览存储的 ``name`` ``body.profile``（因此编辑者可以在保存之前预览），与启动时的
    相同解决和最终化。 在主体中报告悬垂引用（有效值为Fals
    e），而不是抛出错误 — 只有404（未知存储的档案）和422（无效草稿）是错误状态。
    resolved_settings 是已脱敏（没有机密的原始数据）。
    """
    if body is not None and body.profile is not None:
        profile = _validate_profile_payload({**body.profile, "name": name})
    else:
        store = get_agent_profile_store()
        try:
            with store_errors():
                # 关闭事件循环：存储锁等待块（最多 30 秒）。
                profile = await asyncio.to_thread(store.load, name)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent profile '{name}' not found",
            )

    config = get_config(request)
    settings = get_settings_store(config).load() or PersistedSettings()
    context = settings.agent_settings.agent_context
    return await asyncio.to_thread(
        lambda: preview_launch(
            profile,
            server_launch_stores(settings, get_cipher(request)),
            target_launch_runtime(config),
            load_memory=context is not None and context.load_memory,
            check_usable=can_probe_tools(config),
        )
    )
