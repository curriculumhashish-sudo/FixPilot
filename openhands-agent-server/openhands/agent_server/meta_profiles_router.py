"""HTTP CRUD + 激活元配置文件端点（镜像 profiles_router）。

与 LLM 配置文件不同，元配置文件不包含机密 — 它们是通过：class:`MetaProfileStore` 的普
通 JSON 文档已持久化。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, status
from pydantic import AfterValidator, BaseModel

from openhands.agent_server._secrets_exposure import get_config
from openhands.agent_server.persistence import (
    PersistedSettings,
    get_settings_store,
)
from openhands.sdk.llm.llm_profile_store import PROFILE_NAME_PATTERN
from openhands.sdk.llm.meta_profile_store import (
    MetaProfile,
    MetaProfileLimitExceeded,
    MetaProfileStore,
    default_meta_profile_dir,
)
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

meta_profiles_router = APIRouter(prefix="/meta-profiles", tags=["Meta-profiles"])

MAX_META_PROFILES = 50

MetaProfileName = Annotated[
    str,
    Path(min_length=1, max_length=64, pattern=PROFILE_NAME_PATTERN),
]


def _require_route(meta_profile: MetaProfile) -> MetaProfile:
    """拒绝没有任何内容可路由的元配置文件。

    只在保存时检查，而不是在``MetaProfile``本身，因此元配置已经已持久化，没有类或模板
    （存储文件，``settings.json``内的内联复制，会话工具
    参数）仍然加载。
    """
    if not meta_profile.classes and meta_profile.prompt_template is None:
        raise ValueError(
            "A meta-profile needs either classes or a prompt_template to route."
        )
    return meta_profile


RoutableMetaProfile = Annotated[MetaProfile, AfterValidator(_require_route)]


def _get_meta_profile_store() -> MetaProfileStore:
    """解析 ``OH_PERSISTENCE_DIR`` 下的元配置文件存储。

    使用与运行时路由工具相同的帮助程序，因此 HTTP API 和会话执行读/写相同的隔离存储。
    """
    return MetaProfileStore(base_dir=default_meta_profile_dir())


class MetaProfileInfo(BaseModel):
    name: str
    classifier_model: str | None = None
    num_classes: int = 0


class MetaProfileListResponse(BaseModel):
    meta_profiles: list[MetaProfileInfo]
    active_meta_profile: str | None = None


class MetaProfileDetailResponse(BaseModel):
    name: str
    config: MetaProfile


class MetaProfileMutationResponse(BaseModel):
    name: str
    message: str


class ActivateMetaProfileResponse(BaseModel):
    name: str
    message: str
    applied: bool = True
    """False当前智能体设置无法附加布线工具时
    (e.g. ACP），因此没有激活任何内容（在 LLM 配置文件激活上镜像 ``llm_applied``）。
"""


@contextmanager
def _store_errors() -> Iterator[None]:
    """将 ``MetaProfileStore`` 个错误映射到 HTTP 个响应。"""
    try:
        yield
    except TimeoutError:
        # save()/delete() 可以从存在争用的文件锁中提出 TimeoutError； 显示可重试的 503，
        # 而不是通用的 500（镜像 profiles_router._store_errors()）。
        #
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta-profile store is busy. Please retry.",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


def _set_active_meta_profile_if_matches(
    request: Request, old_name: str, new_name: str | None
) -> bool:
    config = get_config(request)
    settings_store = get_settings_store(config)
    settings = settings_store.load() or PersistedSettings()
    if settings.active_meta_profile != old_name:
        return False

    def update_active(settings: PersistedSettings) -> PersistedSettings:
        # 通过 PersistedSettings.update() 进行路由，因此更改也会传播到 agent_settings (
        # active_meta_profile + enable_classify_and_switch_llm_tool)； 直接的字段分配会
        # 使嵌套状态变得陈旧。
        #
        agent_diff = {"meta_profile": None} if new_name is None else {}
        settings.update(
            {
                "active_meta_profile": new_name,
                "agent_settings_diff": agent_diff,
            }
        )
        return settings

    settings_store.update(update_active)
    return True


@meta_profiles_router.get("", response_model=MetaProfileListResponse)
def list_meta_profiles(request: Request) -> MetaProfileListResponse:
    """列出所有已保存的元配置文件和当前活动的元配置文件。"""
    config = get_config(request)
    settings_store = get_settings_store(config)
    settings = settings_store.load() or PersistedSettings()

    store = _get_meta_profile_store()
    with _store_errors():
        summaries = store.list_summaries()

    return MetaProfileListResponse(
        meta_profiles=[MetaProfileInfo(**s) for s in summaries],
        active_meta_profile=settings.active_meta_profile,
    )


@meta_profiles_router.get("/{name}", response_model=MetaProfileDetailResponse)
def get_meta_profile(name: MetaProfileName) -> MetaProfileDetailResponse:
    """获取元配置文件的完整配置。"""
    store = _get_meta_profile_store()
    try:
        with _store_errors():
            meta_profile = store.load(name)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meta-profile '{name}' not found",
        )

    return MetaProfileDetailResponse(name=name, config=meta_profile)


@meta_profiles_router.post(
    "/{name}",
    response_model=MetaProfileMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_meta_profile(
    name: MetaProfileName,
    body: RoutableMetaProfile,
) -> MetaProfileMutationResponse:
    """保存（创建或覆盖）元配置文件。

    如果创建新的元配置文件超出限制，则返回 409
    ``MAX_META_PROFILES``.
    """
    store = _get_meta_profile_store()
    try:
        with _store_errors():
            store.save(name, body, max_profiles=MAX_META_PROFILES)
    except MetaProfileLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Meta-profile limit reached ({MAX_META_PROFILES}). "
                "Delete a meta-profile before saving a new one."
            ),
        )

    logger.info(f"Saved meta-profile '{name}'")
    return MetaProfileMutationResponse(
        name=name, message=f"Meta-profile '{name}' saved"
    )


@meta_profiles_router.delete("/{name}", response_model=MetaProfileMutationResponse)
def delete_meta_profile(
    request: Request, name: MetaProfileName
) -> MetaProfileMutationResponse:
    """删除元配置文件（幂等）。

    如果删除的元配置文件是活动元配置文件，则 ``active_meta_profile`` 被清除。
    """
    store = _get_meta_profile_store()
    with _store_errors():
        store.delete(name)
    if _set_active_meta_profile_if_matches(request, name, None):
        logger.info(f"Cleared active_meta_profile for deleted meta-profile '{name}'")
    logger.info(f"Deleted meta-profile '{name}'")
    return MetaProfileMutationResponse(
        name=name, message=f"Meta-profile '{name}' deleted"
    )


@meta_profiles_router.post(
    "/{name}/activate", response_model=ActivateMetaProfileResponse
)
def activate_meta_profile(
    request: Request, name: MetaProfileName
) -> ActivateMetaProfileResponse:
    """通过将元配置文件记录为 ``active_meta_profile`` 来激活它。

    与 LLM 配置文件不同，激活元配置文件不会改变智能体的 LLM 配置 - 它只记录哪个元配置
    文件
    ``route_task_to_model`` 工具应用于布线。 如果元配置文件不存在，则返回 404。 在智
    能体设置中无法附加布线工具 (e.g. ACP) 没有
    记录任何内容，并且响应已
    ``applied: false``.
    """
    # 在激活之前验证元配置文件是否存在（并且有效）。
    store = _get_meta_profile_store()
    try:
        with _store_errors():
            meta_profile = store.load(name)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meta-profile '{name}' not found",
        )

    config = get_config(request)
    settings_store = get_settings_store(config)
    applied = False

    def apply_active(settings: PersistedSettings) -> PersistedSettings:
        nonlocal applied
        # 通过 PersistedSettings.update() 进行路由，因此激活也会连接 agent_settings (
        # active_meta_profile + enable_classify_and_switch_llm_tool)，这实际上是附加路由
        # 工具的。 直接字段分配将记录活动名称，但永远不会启用该工具。
        #
        settings.update(
            {
                "active_meta_profile": name,
                "agent_settings_diff": {
                    "meta_profile": meta_profile.model_dump(mode="json")
                },
            }
        )
        # 当智能体无法路由 (ACP) 时，``update()`` 会丢弃指针。
        applied = settings.active_meta_profile == name
        return settings

    try:
        settings_store.update(apply_active)
    except (OSError, PermissionError):
        logger.error("Failed to activate meta-profile - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to activate meta-profile")
    except RuntimeError as e:
        logger.error(f"Failed to activate meta-profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Settings file is corrupted or encrypted with a different key",
        )

    if not applied:
        logger.info(f"Meta-profile '{name}' not activated: agent cannot route")
        return ActivateMetaProfileResponse(
            name=name,
            message=(
                f"Meta-profile '{name}' not activated: the current agent "
                "settings cannot route between models"
            ),
            applied=False,
        )
    logger.info(f"Activated meta-profile '{name}'")
    return ActivateMetaProfileResponse(
        name=name, message=f"Meta-profile '{name}' activated"
    )
