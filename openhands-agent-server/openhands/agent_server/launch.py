""":mod:`openhands.sdk.launch` 中启动管道的服务器端。

智能体请求的源被此服务器的存储库所解决，描述了这一过程为``LaunchRuntime``，并为会话容
器的已解决源进行序列化，以完成。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import HTTPException, status
from pydantic import TypeAdapter

from openhands.agent_server.config import (
    DEFAULT_CONVERSATION_IMAGE,
    ACPSkillSourcing,
    Config,
)
from openhands.agent_server.docker_runtime.mediation import materialize_secrets
from openhands.agent_server.persistence import (
    PersistedSettings,
    get_agent_profile_store,
    get_llm_profile_store,
)
from openhands.agent_server.skills_service import (
    discover_profile_skills,
    discover_public_skill_names,
)
from openhands.sdk.agent import ACPAgent
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.conversation.request import StartConversationRequest
from openhands.sdk.launch import (
    AgentLaunchError,
    LaunchRuntime,
    LaunchSource,
    LaunchStoreError,
    LaunchStores,
    ResolvedLaunch,
    resolve,
)
from openhands.sdk.llm.meta_profile_store import (
    MetaProfileStore,
    default_meta_profile_dir,
)
from openhands.sdk.profiles.resolver import ProfileNotFound
from openhands.sdk.secret import SecretSource
from openhands.sdk.settings.model import (
    ACPAgentSettings,
    validate_agent_settings,
)
from openhands.sdk.tool import BROWSER_TOOL_NAME, is_tool_usable
from openhands.sdk.utils.cipher import Cipher


_SECRETS_ADAPTER: TypeAdapter[dict[str, SecretSource]] = TypeAdapter(
    dict[str, SecretSource]
)


def server_launch_stores(
    settings: PersistedSettings, cipher: Cipher | None
) -> LaunchStores:
    llm_store = get_llm_profile_store()
    verification = getattr(settings.agent_settings, "verification", None)
    return LaunchStores(
        llm_profiles=llm_store,
        llm_profile_names=lambda: [n.removesuffix(".json") for n in llm_store.list()],
        mcp_config=settings.agent_settings.mcp_config,
        skills=discover_profile_skills,
        public_skill_names=discover_public_skill_names,
        critic_api_key=verification.critic_api_key if verification else None,
        agent_profiles=get_agent_profile_store(),
        meta_profiles=MetaProfileStore(base_dir=default_meta_profile_dir()),
        cipher=cipher,
    )


def live_launch_runtime(
    acp_skill_sourcing: ACPSkillSourcing, *, enable_browser: bool
) -> LaunchRuntime:
    return LaunchRuntime(
        browser_available=enable_browser and is_tool_usable(BROWSER_TOOL_NAME),
        acp_skill_sourcing=acp_skill_sourcing,
    )


def target_launch_runtime(config: Config) -> LaunchRuntime:
    """描述该服务器启动时运行的运行时，但不启动它。"""
    if config.conversation_runtime == "docker":
        # 容器镜像集托管采购。
        return LaunchRuntime(
            browser_available=container_browser_enabled(config),
            acp_skill_sourcing="openhands_managed",
        )
    return live_launch_runtime(
        config.acp_skill_sourcing, enable_browser=config.enable_browser
    )


def can_probe_tools(config: Config) -> bool:
    """在此过程中是否运行对话，因此可以探测工具的可用性。"""
    return config.conversation_runtime != "docker"


def configured_browser_available(config: Config) -> bool | None:
    """浏览器可用性已由 ``config`` 修复； ``None``表示探测这个过程。"""
    if config.conversation_runtime == "docker":
        return container_browser_enabled(config)
    return None if config.enable_browser else False


def container_browser_enabled(config: Config) -> bool:
    """该服务器的会话容器是否可以获取浏览器。"""
    if not config.enable_browser:
        return False
    if config.conversation_image_has_browser is not None:
        return config.conversation_image_has_browser
    return _is_stock_image(config.conversation_image)


_BROWSERLESS_FLAVOR = re.compile(r"-minimal(-(amd64|arm64))?$")


def _is_stock_image(image: str) -> bool:
    stock_repo = DEFAULT_CONVERSATION_IMAGE.rsplit(":", 1)[0]
    repo = image.split("@", 1)[0]
    tag = ""
    if repo.rfind(":") > repo.rfind("/"):
        repo, tag = repo.rsplit(":", 1)
    return repo == stock_repo and not _BROWSERLESS_FLAVOR.search(tag)


def launch_source(
    request: StartConversationRequest,
    stores: Callable[[], LaunchStores],
    cipher: Cipher | None,
) -> LaunchSource:
    """将请求的智能体源转变为启动源（阻止）。"""
    context = _decryption_context(request, cipher)
    additions = request.agent_launch_additions
    llm_profile_ref = additions.llm_profile_ref if additions else None
    if request.agent_profile_id is not None:
        return resolve(
            request.agent_profile_id, stores(), llm_profile_ref=llm_profile_ref
        )
    agent: AgentBase | None = request.agent
    if agent is not None:
        if context is None:
            return agent
        return type(agent).model_validate(
            agent.model_dump(mode="json", context={"expose_secrets": True}),
            context=context,
        )
    if request.agent_settings is None:
        raise AgentLaunchError("The start request has no agent source")
    try:
        settings = validate_agent_settings(request.agent_settings, context=context)
    except (TypeError, ValueError) as exc:
        raise AgentLaunchError(f"Invalid agent_settings: {exc}") from exc
    return ResolvedLaunch(settings=settings)


def request_secrets(
    request: StartConversationRequest, cipher: Cipher | None
) -> dict[str, SecretSource]:
    """请求的机密，在客户端加密时解密。"""
    context = _decryption_context(request, cipher)
    if context is None:
        return dict(request.secrets)
    return _SECRETS_ADAPTER.validate_python(
        _SECRETS_ADAPTER.dump_python(
            request.secrets, mode="json", context={"expose_secrets": True}
        ),
        context=context,
    )


def _decryption_context(
    request: StartConversationRequest, cipher: Cipher | None
) -> dict[str, Any] | None:
    if not request.secrets_encrypted:
        return None
    if cipher is None:
        raise ValueError(
            "Cannot decrypt secrets: cipher not configured. "
            "Set OH_SECRET_KEY environment variable."
        )
    return {"cipher": cipher}


LaunchFailure = ProfileNotFound | AgentLaunchError | LaunchStoreError


def launch_http_exception(exc: LaunchFailure) -> HTTPException:
    if isinstance(exc, ProfileNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, AgentLaunchError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.to_detail())
    code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if exc.retryable
        else status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    return HTTPException(code, str(exc))


def scoped_secrets(
    secrets: Mapping[str, SecretSource], source: LaunchSource
) -> dict[str, SecretSource]:
    """删除配置文件 ``secret_refs`` 不允许的请求机密。"""
    allowed = source.allowed_secrets if isinstance(source, ResolvedLaunch) else None
    if allowed is None:
        return dict(secrets)
    return {name: value for name, value in secrets.items() if name in allowed}


def is_codex_source(source: LaunchSource) -> bool:
    if isinstance(source, ResolvedLaunch):
        settings = source.settings
        return isinstance(settings, ACPAgentSettings) and settings.acp_server == "codex"
    return isinstance(source, ACPAgent) and source.acp_server == "codex"


def forward_to_runtime(
    request: StartConversationRequest,
    source: LaunchSource | None,
    secrets: Mapping[str, SecretSource],
    cipher: Cipher,
    *,
    load_memory: bool,
) -> dict[str, Any]:
    """序列化对话容器的启动请求以完成。

    ``secrets`` 请求的机密已解密； 那些只有该服务器可以解析的内容被具体化，并且载荷用
    容器的``cipher``加密。 ``source`` None 转发
    请求自己的配置文件源，用于容器已有的对话。
    """
    scoped = secrets if source is None else scoped_secrets(secrets, source)
    forwarded = request.model_copy(
        update={"secrets": materialize_secrets(scoped), "secrets_encrypted": True}
    )
    sources = {"agent", "agent_settings", "agent_profile_id"}
    payload = forwarded.model_dump(
        mode="json",
        context={"cipher": cipher},
        exclude=sources if source is not None else {"agent", "agent_settings"},
    )
    if source is None:
        return payload
    model = source.settings if isinstance(source, ResolvedLaunch) else source
    field = "agent_settings" if isinstance(source, ResolvedLaunch) else "agent"
    payload[field] = model.model_copy(
        update=_forwarded_context(model.agent_context, load_memory=load_memory)
    ).model_dump(mode="json", context={"cipher": cipher})
    additions = dict(payload.get("agent_launch_additions") or {})
    # 已通过解析申请； 没有配置文件源，它是无效的。
    additions.pop("llm_profile_ref", None)
    payload["agent_launch_additions"] = additions or None
    return payload


def _forwarded_context(
    context: AgentContext | None, *, load_memory: bool
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if context is not None and context.secrets:
        updates["secrets"] = materialize_secrets(context.secrets)
    if load_memory:
        updates["load_memory"] = True
    if not updates:
        return {}
    # null 上下文表示“无提示词上下文”，因此合成后不携带时间戳。
    #
    base = context or AgentContext(current_datetime=None)
    return {"agent_context": base.model_copy(update=updates)}
