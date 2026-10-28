from collections.abc import Callable
from functools import lru_cache
from typing import cast

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import ValidationError

from openhands.agent_server._secrets_exposure import (
    build_expose_context,
    get_cipher,
    get_config,
    parse_expose_secrets_header,
    store_errors,
    translate_missing_cipher,
)
from openhands.agent_server.persistence import (
    SECRET_NAME_PATTERN,
    PersistedSettings,
    get_agent_profile_store,
    get_llm_profile_store,
    get_secrets_store,
    get_settings_store,
)
from openhands.agent_server.persistence.models import SettingsUpdatePayload
from openhands.agent_server.telemetry import notify_misc_settings_changed
from openhands.sdk.llm import LLM
from openhands.sdk.llm.meta_profile_store import (
    MetaProfileStore,
    default_meta_profile_dir,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.settings import (
    ConversationSettings,
    SecretCreateRequest,
    SecretItemResponse,
    SecretsListResponse,
    SettingsResponse,
    SettingsSchema,
    SettingsUpdateRequest,
    export_agent_settings_schema,
)
from openhands.sdk.settings.api_models import MCPServerPatch
from openhands.sdk.utils.pydantic_secrets import is_redacted_secret


logger = get_logger(__name__)

# ── 路由路径常量 ───────────────────────────────────────────────── 这些是相对于路由器前
# 缀的(/settings). 当在/api上挂载时，完整的路径变为/api/settings、/api/settings/secrets
# 等。
# 注意：RemoteWorkspace（客户端）使用绝对路径（e.g., "/api/settings")
# while this router uses relative paths. The paths are intentionally separate
# 匹配它们各自的上下文（路由器前缀与完整的 URL 路径）。
SETTINGS_PATH = ""  # -> /api/settings
MCP_SERVER_PATH = "/mcp/{settings_key}"  # -> /api/settings/mcp/{settings_key}
SECRETS_PATH = "/secrets"  # -> /api/settings/secrets
SECRET_VALUE_PATH = "/secrets/{name}"  # -> /api/settings/secrets/{name}

settings_router = APIRouter(prefix="/settings", tags=["Settings"])


# ── 模式端点 ─────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent_settings_schema() -> SettingsSchema:
    # ``AgentSettings`` 现在是一个受歧视的工会
    # ``OpenHandsAgentSettings``和``ACPAgentSettings``； 将模式标签部分与 ``variant`` 组
    # 合在一起，以便前端可以根据活动显示仅 LLM 或仅 ACP 部分
    # ``agent_kind`` 值。
    return export_agent_settings_schema()


@lru_cache(maxsize=1)
def _get_conversation_settings_schema() -> SettingsSchema:
    return ConversationSettings.export_schema()


@settings_router.get("/agent-schema", response_model=SettingsSchema)
async def get_agent_settings_schema() -> SettingsSchema:
    """返回用于呈现基于 AgentSettings 的设置表单的模式。"""
    return _get_agent_settings_schema()


@settings_router.get("/conversation-schema", response_model=SettingsSchema)
async def get_conversation_settings_schema() -> SettingsSchema:
    """返回用于呈现基于 ConversationSettings 的表单的模式。"""
    return _get_conversation_settings_schema()


# ── 设定CRUD端点 ──────────────────────────────────────────────


def _validate_secret_name(name: str) -> None:
    """验证机密名称格式。

    机密姓名必须：
    - 以字母开头
    - 仅包含字母、数字和下划线
    - 长度为 1-64 个字符

    Raises:
        HTTPException: 422 如果名称格式无效。
    """
    if not SECRET_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid secret name format. Must start with a letter, "
                "contain only letters, numbers, and underscores, "
                "and be 1-64 characters long."
            ),
        )


@settings_router.get(SETTINGS_PATH, response_model=SettingsResponse)
async def get_settings(request: Request) -> SettingsResponse:
    """获取当前设置。

    返回已持久化设置，包括智能体配置、对话设置以及是否配置 LLM API 键。

    使用 ``X-Expose-Secrets`` 标头控制机密曝光：
    - ``encrypted``：返回密码加密值（对于前端客户端来说是安全的）
    - ``plaintext``：返回原始机密值（仅限后端客户端！）
    - （不存在）：返回已脱敏个值（“**********”）

    安全性：
        当服务器配置为``session_api_keys``时，``/api``下的所有端点（包括这个）都需要
        ``X-Session-API-Key``标头。 当
        未配置会话 API 键时，端点打开。

        **信任模型：**所有经过身份验证的客户端都被平等对待
        值得信赖。 ``X-Expose-Secrets`` 模式没有基于角色的授权——任何经过身份验证的客
        户端都可以请求 ``plaintext`` 或
        ``encrypted`` 曝光。 该设计假设：

        - 所有共享会话 API 密钥的客户端都在同一信任域中运行
        - 网络级控制（防火墙，IDS，IPS） VPCs仅允许受信任的客户端访问
        - 生产部署使用会话 API 密钥来防止匿名访问

        ``plaintext`` 模式用于后端到后端通信（e.g.、RemoteWorkspace）。 前端客户端应
        该更喜欢 ``encrypted`` 模式进行
        往返机密，或者省略标头以接收已脱敏值。
    """
    expose_mode = parse_expose_secrets_header(request)
    config = get_config(request)
    store = get_settings_store(config)
    settings = store.load() or PersistedSettings()

    # 审核日志所有设置访问以实现安全可见性使用警告级别进行明文模式以突出显示安全敏感操作
    #
    client_host = request.client.host if request.client else "unknown"
    log_extra = {
        "client_host": client_host,
        "expose_mode": expose_mode or "redacted",
        "has_llm_api_key": settings.llm_api_key_is_set,
    }
    if expose_mode == "plaintext":
        logger.warning("Settings accessed with PLAINTEXT secrets", extra=log_extra)
    else:
        logger.info("Settings accessed", extra=log_extra)

    context = build_expose_context(expose_mode, config.cipher)
    with translate_missing_cipher():
        return SettingsResponse(
            agent_settings=settings.agent_settings.model_dump(
                mode="json", context=context
            ),
            conversation_settings=settings.conversation_settings.model_dump(
                mode="json"
            ),
            llm_api_key_is_set=settings.llm_api_key_is_set,
            active_profile=settings.active_profile,
            active_agent_profile_id=settings.active_agent_profile_id,
            active_meta_profile=settings.active_meta_profile,
            misc_settings=settings.misc_settings,
        )


@settings_router.patch(SETTINGS_PATH, response_model=SettingsResponse)
def update_settings(
    request: Request, payload: SettingsUpdateRequest
) -> SettingsResponse:
    """通过部分更改更新设置。

    接受 ``agent_settings_diff``、``conversation_settings_diff``、
    ``misc_settings_diff`` 和/或 ``active_profile`` 用于增量更新。 设置
    ``active_profile`` 加载并应用该
    配置文件的 LLM，与
    ``POST /api/profiles/{name}/activate``，除非还给出了 ``agent_settings_diff.llm``
    。

    三个``*_settings_diff``字段深度合并； 嵌套对象递归合并，``null``值**在嵌套的**map
    中删除了该条目——“unset”基本类型，它允许
    客户端不反向传输整个map，仅删除单个map键。 删除一台 MCP 服务器的标头：:

        PATCH /api/settings
        {"agent_settings_diff":
            {"mcp_config": {"svc": {"headers": {"X-Old": null}}}}}

    顶级 * 字段 * 上的 ``null`` (e.g. ``{"confirmation_mode": null}``) 是 ** 而不是
    ** 未设置 — 它像以
    前一样流向模型验证，因此它仍然会大声失败，而不是默默地将字段重置为其默认值。

    ``misc_settings_diff`` 深度合并到已持久化 ``misc_settings`` 块中。 智能体-服务器
    将 ``misc_settings``
    视为不透明的前端拥有的
    data: 嵌套字典被递归合并，列表被批量替换，
    并且内容永远不会在服务器端读取或验证。

    使用文件锁定来防止并发更新相互覆盖。

    非 null ``active_agent_profile_id`` 或 ``active_meta_profile`` 必须命名存储的配置
    文件，就像它们的
    ``/activate`` 路由一样； ``null`` 清除指针。

    Raises:
        HTTPException: 如果 update 载荷包含无效值，则返回 400；
            404如果 ``active_profile``, ``active_agent_profile_id`` 或
            ``active_meta_profile`` 命名了一个不存在的配置文件。
    """
    update_data = payload.model_dump(exclude_none=True)
    # exclude_none 删除了显式的 null，因此当客户端设置可空指针（包括 None）以允许清除时
    # ，请重新添加可空指针。
    #
    if "active_profile" in payload.model_fields_set:
        update_data["active_profile"] = payload.active_profile
    if "active_agent_profile_id" in payload.model_fields_set:
        update_data["active_agent_profile_id"] = payload.active_agent_profile_id
    if "active_meta_profile" in payload.model_fields_set:
        update_data["active_meta_profile"] = payload.active_meta_profile
    if not update_data:
        # 未提供更新 - 这是客户端错误
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one of agent_settings_diff, "
                "conversation_settings_diff, misc_settings_diff, "
                "active_profile, active_agent_profile_id, or active_meta_profile "
                "must be provided"
            ),
        )

    _require_pointer_targets(update_data)
    return _apply_settings_update(
        request,
        cast(SettingsUpdatePayload, update_data),
    )


def _require_pointer_targets(update_data: dict) -> None:
    """拒绝没有任何名称的智能体-profile / 元配置文件指针。

    镜子 ``POST /api/agent-profiles/{id}/activate`` 和
    ``POST /api/meta-profiles/{name}/activate`` (404). ``None`` 清除。
    """
    profile_id = update_data.get("active_agent_profile_id")
    if profile_id is not None:
        with store_errors():
            known = get_agent_profile_store().name_for_id(profile_id) is not None
        if not known:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent profile with id '{profile_id}' not found",
            )

    meta_name = update_data.get("active_meta_profile")
    if meta_name is not None:
        try:
            with store_errors():
                MetaProfileStore(base_dir=default_meta_profile_dir()).load(meta_name)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meta-profile '{meta_name}' not found",
            )


def _load_active_profile_llm(
    request: Request, update_data: SettingsUpdatePayload
) -> LLM | None:
    """加载指定配置文件的 LLM，除非调用者已经给出了一个。"""
    profile_name = update_data.get("active_profile")
    agent_diff = update_data.get("agent_settings_diff")
    explicit_llm_diff = isinstance(agent_diff, dict) and "llm" in agent_diff
    if not profile_name or explicit_llm_diff:
        return None

    cipher = get_cipher(request)
    profile_store = get_llm_profile_store()
    # ``load`` 解析任何引用的提供者连接（使用时读取）； 悬空引用引发
    # ProviderConnectionNotFound，其中 store_errors() 映射到 422。
    #
    try:
        with store_errors():
            llm = profile_store.load(profile_name, cipher=cipher)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile_name}' not found",
        )
    return llm


def _with_profile_llm(
    update_data: SettingsUpdatePayload,
    llm: LLM | None,
    settings: PersistedSettings,
) -> SettingsUpdatePayload:
    """将配置文件的 LLM 折叠到 OpenHands 设置中。 镜子``/activate``。"""
    agent_diff = update_data.get("agent_settings_diff")
    agent_diff = agent_diff if isinstance(agent_diff, dict) else {}
    agent_kind = agent_diff.get("agent_kind") or settings.agent_settings.agent_kind
    if llm is None or agent_kind == "acp":
        return update_data
    return cast(
        SettingsUpdatePayload,
        {
            **update_data,
            "agent_settings_diff": {
                **agent_diff,
                "llm": llm.model_dump(mode="json", context={"expose_secrets": True}),
            },
        },
    )


def _apply_settings_update(
    request: Request,
    update_data: SettingsUpdatePayload,
    before_update: Callable[[PersistedSettings], None] | None = None,
) -> SettingsResponse:
    profile_llm = _load_active_profile_llm(request, update_data)
    applied_update = update_data

    # 通过文件锁定自动应用更新
    def apply_update(settings: PersistedSettings) -> PersistedSettings:
        nonlocal applied_update
        if before_update is not None:
            before_update(settings)
        context = {"cipher": config.cipher} if config.cipher is not None else None
        applied_update = _with_profile_llm(update_data, profile_llm, settings)
        settings.update(applied_update, context=context)
        return settings

    config = get_config(request)
    store = get_settings_store(config)
    client_host = request.client.host if request.client else "unknown"
    try:
        settings = store.update(apply_update)
        # 审核日志：设置已修改
        logger.info(
            "Settings updated",
            extra={
                "client_host": client_host,
                "agent_settings_modified": "agent_settings_diff" in applied_update,
                "conversation_settings_modified": (
                    "conversation_settings_diff" in update_data
                ),
                "misc_settings_modified": "misc_settings_diff" in update_data,
            },
        )
        # 同意存在于 misc_settings.telemetry.consent 中，因此设置写入是其更改的唯一方式
        # 。 在返回之前重新解析：撤销必须阻止交付并丢弃队列，而不是在调用者仍在等待时在
        # sink的下一次刷新时。
        #
        if "misc_settings_diff" in update_data:
            notify_misc_settings_changed(settings.misc_settings)
    except (ValueError, ValidationError):
        # 审核日志：验证失败
        # 注意：PersistedSettings.update() 引发 ValueError（已清理的消息）
        # while Pydantic validation raises ValidationError
        logger.warning(
            "Settings update validation failed",
            extra={"client_host": client_host},
        )
        # 422 无法处理的实体 - 语义验证失败不要公开错误详细信息 - 回溯中可能包含机密
        #
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Settings validation failed",
        )
    except RuntimeError as e:
        # 数据损坏保护已触发（文件存在但不可读）
        logger.error(f"Settings update blocked: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Settings file is corrupted or encrypted with a different key: "
                "restore that key as OH_SECRET_KEY or add it to "
                "OH_PREVIOUS_SECRET_KEYS"
            ),
        )
    except (OSError, PermissionError):
        # 注意：省略 exc_info 以防止范围内的机密在回溯中泄漏
        logger.error("Settings update failed - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to update settings")

    # 不要在突变响应中暴露机密（与 GET 行为一致）
    return SettingsResponse(
        agent_settings=settings.agent_settings.model_dump(mode="json"),
        conversation_settings=settings.conversation_settings.model_dump(mode="json"),
        llm_api_key_is_set=settings.llm_api_key_is_set,
        active_profile=settings.active_profile,
        active_agent_profile_id=settings.active_agent_profile_id,
        active_meta_profile=settings.active_meta_profile,
        misc_settings=settings.misc_settings,
    )


def _require_mcp_server_absent(settings: PersistedSettings, settings_key: str) -> None:
    if settings_key in settings.agent_settings.mcp_config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"MCP server '{settings_key}' already exists",
        )


def _require_mcp_server_present(settings: PersistedSettings, settings_key: str) -> None:
    if settings_key not in settings.agent_settings.mcp_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{settings_key}' was not found",
        )


@settings_router.post(
    MCP_SERVER_PATH,
    response_model=SettingsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mcp_server(
    request: Request,
    settings_key: str,
    server: MCPServer,
) -> SettingsResponse:
    """创建一个名为 MCP 的服务器，而不替换现有的映射条目。"""
    server_data = server.model_dump(
        mode="python",
        context={"expose_secrets": "plaintext"},
        exclude_none=True,
        exclude_defaults=True,
    )
    update_data = cast(
        SettingsUpdatePayload,
        {"agent_settings_diff": {"mcp_config": {settings_key: server_data}}},
    )
    return _apply_settings_update(
        request,
        update_data,
        lambda settings: _require_mcp_server_absent(settings, settings_key),
    )


@settings_router.patch(MCP_SERVER_PATH, response_model=SettingsResponse)
async def patch_mcp_server(
    request: Request,
    settings_key: str,
    patch: MCPServerPatch,
) -> SettingsResponse:
    """稀疏地更新一台现有的名为 MCP 的服务器。"""
    patch_data = patch.model_dump(
        mode="python",
        context={"expose_secrets": "plaintext"},
        exclude_unset=True,
    )
    update_data = cast(
        SettingsUpdatePayload,
        {"agent_settings_diff": {"mcp_config": {settings_key: patch_data}}},
    )
    return _apply_settings_update(
        request,
        update_data,
        lambda settings: _require_mcp_server_present(settings, settings_key),
    )


@settings_router.delete(MCP_SERVER_PATH, response_model=SettingsResponse)
async def delete_mcp_server(request: Request, settings_key: str) -> SettingsResponse:
    """删除一台现有的名为 MCP 服务器而不更改同级条目。"""
    update_data = cast(
        SettingsUpdatePayload,
        {"agent_settings_diff": {"mcp_config": {settings_key: None}}},
    )
    return _apply_settings_update(
        request,
        update_data,
        lambda settings: _require_mcp_server_present(settings, settings_key),
    )


# ── 机密 CRUD 端点 ───────────────────────────────────────────────


@settings_router.get(SECRETS_PATH, response_model=SecretsListResponse)
def list_secrets(
    request: Request, agent_profile_id: str | None = None
) -> SecretsListResponse:
    """列出可用的机密名称，可以选择由智能体配置文件限定范围。"""
    config = get_config(request)
    store = get_secrets_store(config)
    secrets = store.load()

    allowed_names: set[str] | None = None
    if agent_profile_id is not None:
        profile_store = get_agent_profile_store()
        # store_errors() 按照智能体-配置文件路由的方式应答不可加载的配置文件 (400) 和繁
        # 忙的存储 (503)。
        #
        with store_errors():
            profile_name = profile_store.name_for_id(agent_profile_id)
            if profile_name is None:
                raise HTTPException(status_code=404, detail="Agent profile not found")
            profile = profile_store.load(profile_name)
        if profile.secret_refs is not None:
            allowed_names = set(profile.secret_refs)

    client_host = request.client.host if request.client else "unknown"
    secret_count = len(secrets.custom_secrets) if secrets else 0
    logger.info(
        "Secrets list accessed",
        extra={"client_host": client_host, "secret_count": secret_count},
    )

    if secrets is None:
        return SecretsListResponse(secrets=[])

    return SecretsListResponse(
        secrets=[
            SecretItemResponse(name=name, description=secret.description)
            for name, secret in secrets.custom_secrets.items()
            if allowed_names is None or name in allowed_names
        ]
    )


@settings_router.get(SECRET_VALUE_PATH)
async def get_secret_value(request: Request, name: str) -> Response:
    """按名称获取单个机密值。

    以纯文本形式返回原始机密值。 此端点设计为与 LookupSecret 一起使用以实现惰性机密分
    辨率。

    Raises:
        HTTPException: 如果名称格式无效，则为 422；如果未找到机密，则为 404。
    """
    _validate_secret_name(name)

    config = get_config(request)
    store = get_secrets_store(config)
    value = store.get_secret(name)

    client_host = request.client.host if request.client else "unknown"
    if value is None:
        # 记录失败的访问尝试以检测枚举攻击
        logger.warning(
            "Secret access failed - not found",
            extra={"secret_name": name, "client_host": client_host},
        )
        # 使用通用消息防止机密名称枚举攻击
        raise HTTPException(status_code=404, detail="Secret not found")

    logger.info(
        "Secret accessed",
        extra={"secret_name": name, "client_host": client_host},
    )
    return Response(content=value, media_type="text/plain")


@settings_router.put(SECRETS_PATH, response_model=SecretItemResponse)
async def create_secret(
    request: Request, secret: SecretCreateRequest
) -> SecretItemResponse:
    """创建或更新自定义机密（更新插入）。

    Raises:
        HTTPException: 如果名称或值无效，则为 422；如果文件已损坏，则为 500。
    """
    _validate_secret_name(secret.name)

    value = secret.value.get_secret_value()
    if not value.strip() or is_redacted_secret(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Secret value must not be empty or redacted",
        )

    config = get_config(request)
    store = get_secrets_store(config)

    try:
        store.set_secret(
            name=secret.name,
            value=value,
            description=secret.description,
        )
    except RuntimeError as e:
        # 数据损坏保护已触发（文件存在但不可读）
        logger.error(f"Secret create blocked: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                "Secrets file is corrupted or encrypted with a different key: "
                "restore that key as OH_SECRET_KEY or add it to "
                "OH_PREVIOUS_SECRET_KEYS"
            ),
        )
    except (OSError, PermissionError):
        # 注意：省略 exc_info 以防止机密值在回溯中泄漏
        logger.error("Failed to save secret - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to save secret")

    logger.info(
        "Secret created/updated",
        extra={
            "secret_name": secret.name,
            "client_host": request.client.host if request.client else "unknown",
        },
    )
    return SecretItemResponse(name=secret.name, description=secret.description)


@settings_router.delete(SECRET_VALUE_PATH)
async def delete_secret(request: Request, name: str) -> dict[str, bool]:
    """按名称删除自定义机密。

    Raises:
        HTTPException: 422 如果名称格式无效，404 如果未找到机密，
        如果文件损坏，则返回 500。
    """
    _validate_secret_name(name)

    config = get_config(request)
    store = get_secrets_store(config)

    client_host = request.client.host if request.client else "unknown"
    try:
        deleted = store.delete_secret(name)
    except RuntimeError as e:
        # 数据损坏保护已触发（文件存在但不可读）
        logger.error(f"Secret delete blocked: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                "Secrets file is corrupted or encrypted with a different key: "
                "restore that key as OH_SECRET_KEY or add it to "
                "OH_PREVIOUS_SECRET_KEYS"
            ),
        )

    if not deleted:
        # 记录失败的删除尝试以检测枚举攻击
        logger.warning(
            "Secret deletion failed - not found",
            extra={"secret_name": name, "client_host": client_host},
        )
        # 使用通用消息防止机密名称枚举攻击
        raise HTTPException(status_code=404, detail="Secret not found")

    logger.info(
        "Secret deleted",
        extra={"secret_name": name, "client_host": client_host},
    )
    return {"deleted": True}
