"""OpenHands SDK 的对话路由器。"""

import json
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import TypeAdapter, ValidationError

from openhands.agent_server._secrets_exposure import (
    decrypt_incoming_llm_secrets,
    get_cipher,
    store_errors,
)
from openhands.agent_server.conversation_registry import ConversationRegistry
from openhands.agent_server.conversation_service import (
    ConversationService,
    InvalidParentConversation,
    UnavailableAgentTool,
)
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.event_service import CondensationUnavailable
from openhands.agent_server.launch import launch_http_exception
from openhands.agent_server.models import (
    INCLUDE_SKILLS_PARAM_TITLE,
    AgentResponseResult,
    AskAgentRequest,
    AskAgentResponse,
    ConversationInfo,
    ConversationPage,
    ConversationRuntimeInfo,
    ConversationRuntimeStatus,
    ConversationSortOrder,
    ForkConversationRequest,
    NavigateConversationRequest,
    SetConfirmationPolicyRequest,
    SetSecurityAnalyzerRequest,
    StartChildConversationRequest,
    StartChildConversationResponse,
    StartConversationRequest,
    StartGoalRequest,
    Success,
    UpdateConversationRequest,
    UpdateSecretsRequest,
    trim_conversation_response_skills,
)
from openhands.agent_server.persistence import get_llm_profile_store
from openhands.sdk import LLM
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.conversation.types import (
    ConversationObservabilityMetadata,
    ConversationObservabilitySpanName,
    ConversationObservabilityTags,
)
from openhands.sdk.launch import AgentLaunchError, LaunchStoreError
from openhands.sdk.marketplace.registry import (
    MarketplaceNotFoundError,
    PluginNotFoundError,
    PluginResolutionError,
)
from openhands.sdk.plugin import PluginFetchError
from openhands.sdk.profiles.resolver import ProfileNotFound
from openhands.sdk.tool.client_tool import ClientToolRegistrationError


conversation_catalog_router = APIRouter(prefix="/conversations", tags=["Conversations"])
conversation_router = APIRouter(prefix="/conversations", tags=["Conversations"])
_OBSERVABILITY_SPAN_NAME_ADAPTER = TypeAdapter(ConversationObservabilitySpanName)
_OBSERVABILITY_TAGS_ADAPTER = TypeAdapter(ConversationObservabilityTags)
_OBSERVABILITY_METADATA_ADAPTER = TypeAdapter(ConversationObservabilityMetadata)


def _request_with_observability_headers(
    request: StartConversationRequest,
    *,
    span_name: str | None,
    tags: str | None,
    metadata: str | None,
    parent_span_context: str | None,
) -> StartConversationRequest:
    updates: dict[str, object] = {}
    try:
        if span_name and "observability_span_name" not in request.model_fields_set:
            updates["observability_span_name"] = (
                _OBSERVABILITY_SPAN_NAME_ADAPTER.validate_python(span_name)
            )
        if tags and "observability_tags" not in request.model_fields_set:
            tag_values = [tag.strip() for tag in tags.split(",") if tag.strip()]
            updates["observability_tags"] = _OBSERVABILITY_TAGS_ADAPTER.validate_python(
                tag_values
            )
        if metadata:
            metadata_payload = json.loads(metadata)
            header_metadata = _OBSERVABILITY_METADATA_ADAPTER.validate_python(
                metadata_payload
            )
            updates["observability_metadata"] = {
                **header_metadata,
                **request.observability_metadata,
            }
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail="X-OpenHands-Observability-Metadata must be a JSON object",
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_context=False),
        ) from exc
    if parent_span_context and not request.observability_parent_span_context:
        updates["observability_parent_span_context"] = parent_span_context
    return request.model_copy(update=updates) if updates else request


# 示例

START_CONVERSATION_EXAMPLES = [
    {
        "agent_settings": {
            "llm": {
                "usage_id": "your-llm-service",
                "model": "your-model-provider/your-model-name",
                "api_key": "your-api-key-here",
            },
        },
        "workspace": {"working_dir": "workspace/project"},
        "initial_message": {
            "role": "user",
            "content": [{"type": "text", "text": "Flip a coin!"}],
        },
    }
]


# 读取方法


def _with_runtime_info(
    request: Request, conversation: ConversationInfo
) -> ConversationInfo:
    registry = getattr(request.app.state, "conversation_registry", None)
    if not isinstance(registry, ConversationRegistry):
        return conversation
    return conversation.model_copy(
        update={"runtime_info": registry.runtime_info(conversation.id)}
    )


@conversation_catalog_router.get("/search", include_in_schema=False)
@conversation_router.get("/search")
async def search_conversations(
    request: Request,
    page_id: Annotated[
        str | None,
        Query(title="Optional next_page_id from the previously returned page"),
    ] = None,
    limit: Annotated[
        int,
        Query(title="The max number of results in the page", gt=0, le=100),
    ] = 100,
    status: Annotated[
        ConversationExecutionStatus | None,
        Query(title="Optional filter by conversation execution status"),
    ] = None,
    sort_order: Annotated[
        ConversationSortOrder,
        Query(title="Sort order for conversations"),
    ] = ConversationSortOrder.CREATED_AT_DESC,
    include_skills: Annotated[bool, Query(title=INCLUDE_SKILLS_PARAM_TITLE)] = False,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationPage:
    """搜索/列出对话"""
    page = await conversation_service.search_conversations(
        page_id, limit, status, sort_order
    )
    if not include_skills:
        # ``model_copy`` 而不是在源服务给我们的东西上进行原地修改，因此我们从不写回源服
        # 务给我们的东西（对于缓存其返回值的服务，包括我们自己） ``AsyncMock`` 用于路由
        # 测试。
        #
        page = page.model_copy(
            update={
                "items": [
                    trim_conversation_response_skills(item) for item in page.items
                ]
            }
        )
    page = page.model_copy(
        update={"items": [_with_runtime_info(request, item) for item in page.items]}
    )
    return page


@conversation_catalog_router.get("/count", include_in_schema=False)
@conversation_router.get("/count")
async def count_conversations(
    status: Annotated[
        ConversationExecutionStatus | None,
        Query(title="Optional filter by conversation execution status"),
    ] = None,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> int:
    """计算与给定过滤器匹配的对话数量"""
    count = await conversation_service.count_conversations(status)
    return count


@conversation_router.get(
    "/{conversation_id}", responses={404: {"description": "Item not found"}}
)
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    include_skills: Annotated[bool, Query(title=INCLUDE_SKILLS_PARAM_TITLE)] = False,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationInfo:
    """给定一个 id，进行对话"""
    conversation = await conversation_service.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not include_skills:
        conversation = trim_conversation_response_skills(conversation)
    return _with_runtime_info(request, conversation)


@conversation_router.get("/{conversation_id}/runtime")
async def get_local_conversation_runtime(
    conversation_id: UUID,
    request: Request,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationRuntimeInfo:
    """检查始终可用的进程内运行时。"""
    if await conversation_service.get_conversation(conversation_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    registry = getattr(request.app.state, "conversation_registry", None)
    if isinstance(registry, ConversationRegistry):
        return registry.runtime_info(conversation_id)
    return ConversationRuntimeInfo(
        runtime_status=ConversationRuntimeStatus.AVAILABLE, can_resume=True
    )


@conversation_router.post("/{conversation_id}/runtime/reprovision")
async def reprovision_local_conversation_runtime(
    conversation_id: UUID,
    request: Request,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationRuntimeInfo:
    """返回本地运行时状态； 本地模式无需提供基础设施。"""
    return await get_local_conversation_runtime(
        conversation_id, request, conversation_service
    )


@conversation_router.get(
    "/{conversation_id}/agent_final_response",
    responses={404: {"description": "Conversation not found"}},
)
async def get_conversation_agent_final_response(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> AgentResponseResult:
    """获取智能体对对话的最终回复。

    返回最后一个智能体完成消息 (FinishAction) 或最后一个智能体文本响应 (MessageEvent)
     的文本。 如果智能体尚未产生最终响应，则返回空字符
    串。
    """
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    response = await event_service.get_agent_final_response()
    return AgentResponseResult(response=response)


@conversation_router.get("")
async def batch_get_conversations(
    request: Request,
    ids: Annotated[list[UUID], Query(max_length=99)],
    include_skills: Annotated[bool, Query(title=INCLUDE_SKILLS_PARAM_TITLE)] = False,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationInfo | None]:
    """根据给定的 id 获取一批最多 99 个对话，返回 null
    对于任何缺失的物品"""
    conversations = await conversation_service.batch_get_conversations(ids)
    conversations = [
        _with_runtime_info(request, conversation) if conversation is not None else None
        for conversation in conversations
    ]
    if not include_skills:
        return [
            trim_conversation_response_skills(c) if c is not None else None
            for c in conversations
        ]
    return conversations


# 编写方法


@conversation_router.post(
    "", responses={429: {"description": "Server conversation run capacity is full"}}
)
async def start_conversation(
    request: Annotated[
        StartConversationRequest, Body(examples=START_CONVERSATION_EXAMPLES)
    ],
    response: Response,
    include_skills: Annotated[bool, Query(title=INCLUDE_SKILLS_PARAM_TITLE)] = False,
    x_openhands_observability_span_name: Annotated[
        str | None, Header(alias="X-OpenHands-Observability-Span-Name")
    ] = None,
    x_openhands_observability_tags: Annotated[
        str | None, Header(alias="X-OpenHands-Observability-Tags")
    ] = None,
    x_openhands_observability_metadata: Annotated[
        str | None, Header(alias="X-OpenHands-Observability-Metadata")
    ] = None,
    x_openhands_observability_parent_span_context: Annotated[
        str | None, Header(alias="X-OpenHands-Observability-Parent-Span-Context")
    ] = None,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationInfo:
    """在本地环境中开始对话。"""
    if request.conversation_runtime not in (None, "local"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This server only runs local conversations",
        )
    request = _request_with_observability_headers(
        request,
        span_name=x_openhands_observability_span_name,
        tags=x_openhands_observability_tags,
        metadata=x_openhands_observability_metadata,
        parent_span_context=x_openhands_observability_parent_span_context,
    )
    try:
        info, is_new = await conversation_service.start_conversation(request)
    except (ProfileNotFound, AgentLaunchError, LaunchStoreError) as e:
        raise launch_http_exception(e) from e
    except ClientToolRegistrationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e
    except (InvalidParentConversation, UnavailableAgentTool) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    if not include_skills:
        info = trim_conversation_response_skills(info)
    return info


@conversation_router.post(
    "/{conversation_id}/pause", responses={404: {"description": "Item not found"}}
)
async def pause_conversation(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """暂停对话，以便稍后恢复。"""
    paused = await conversation_service.pause_conversation(conversation_id)
    if not paused:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return Success()


@conversation_router.post(
    "/{conversation_id}/interrupt",
    responses={404: {"description": "Item not found"}},
)
async def interrupt_conversation(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """立即打断正在进行的对话。

    不像 ``/pause``, 这个等待当前 LLM 呼叫结束，
    ``/interrupt`` 取消正在进行的请求，因此效果是即时的。 对话将转换为 * 已暂停 *，稍
    后可以恢复。
    """
    interrupted = await conversation_service.interrupt_conversation(conversation_id)
    if not interrupted:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return Success()


@conversation_router.delete(
    "/{conversation_id}", responses={404: {"description": "Item not found"}}
)
async def delete_conversation(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """永久删除对话。"""
    deleted = await conversation_service.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return Success()


@conversation_router.post(
    "/{conversation_id}/run",
    responses={
        404: {"description": "Item not found"},
        409: {"description": "Conversation is already running"},
        429: {"description": "Server conversation run capacity is full"},
    },
)
async def run_conversation(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """开始在后台运行对话。"""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    try:
        await event_service.run()
    except ValueError as e:
        if str(e) == "conversation_already_running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Conversation already running. Wait for completion or pause first."
                ),
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return Success()


@conversation_router.post(
    "/{conversation_id}/goal",
    responses={
        404: {"description": "Item not found"},
        409: {"description": "Conversation run or goal loop is already running"},
        429: {"description": "Server conversation run capacity is full"},
    },
)
async def start_goal_in_conversation(
    conversation_id: UUID,
    request: StartGoalRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """在现有对话中启动 ``/goal`` 循环。

    循环附加消息并开始智能体在与主聊天相同的对话历史记录和事件流中运行。 它不会为目标
    创建单独的对话，也不会分叉现有的对话。
    """
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    try:
        await event_service.start_goal_loop(
            request.objective, max_iterations=request.max_iterations
        )
    except ValueError as e:
        message = str(e)
        if message in ("conversation_already_running", "goal_already_running"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conversation run or goal loop already running.",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return Success()


@conversation_router.post(
    "/{conversation_id}/goal/stop",
    responses={404: {"description": "Item not found"}},
)
async def stop_goal_in_conversation(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """停止此对话中的活动 ``/goal`` 循环。

    这仅取消后台目标循环，而不是对话本身，并记录 ``interrupted`` 目标状态，以便
    ``/goal/resume`` 可以继续它。
    """
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await event_service.stop_goal_loop()
    return Success()


@conversation_router.post(
    "/{conversation_id}/goal/resume",
    responses={
        404: {"description": "Item not found"},
        409: {"description": "Conversation run or goal loop is already running"},
        429: {"description": "Server conversation run capacity is full"},
    },
)
async def resume_goal_in_conversation(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """恢复此对话中最后一个中断的 ``/goal`` 循环。"""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    try:
        await event_service.resume_goal_loop()
    except ValueError as e:
        message = str(e)
        if message in ("conversation_already_running", "goal_already_running"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conversation run or goal loop already running.",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return Success()


@conversation_router.post(
    "/{conversation_id}/secrets", responses={404: {"description": "Item not found"}}
)
async def update_conversation_secrets(
    conversation_id: UUID,
    request: UpdateSecretsRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """更新对话的机密。"""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # 字符串有效 SecretValue (SecretValue = str | SecretProvider)
    from typing import cast

    from openhands.sdk.conversation.secret_registry import SecretValue

    secrets = cast(dict[str, SecretValue], request.secrets)
    await event_service.update_secrets(secrets)
    return Success()


@conversation_router.post(
    "/{conversation_id}/confirmation_policy",
    responses={404: {"description": "Item not found"}},
)
async def set_conversation_confirmation_policy(
    conversation_id: UUID,
    request: SetConfirmationPolicyRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """设置对话的确认策略。"""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await event_service.set_confirmation_policy(request.policy)
    return Success()


@conversation_router.post(
    "/{conversation_id}/security_analyzer",
    responses={404: {"description": "Item not found"}},
)
async def set_conversation_security_analyzer(
    conversation_id: UUID,
    request: SetSecurityAnalyzerRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """设置对话的安全分析器。"""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await event_service.set_security_analyzer(request.security_analyzer)
    return Success()


@conversation_router.post(
    "/{conversation_id}/switch_profile",
    responses={
        400: {"description": "Invalid or corrupted profile"},
        404: {"description": "Conversation or profile not found"},
    },
)
async def switch_conversation_profile(
    conversation_id: UUID,
    profile_name: str = Body(..., embed=True),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """将对话的 LLM 配置文件切换到命名配置文件。"""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    conversation = event_service.get_conversation()
    try:
        conversation.switch_profile(profile_name)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile_name}' not found",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return Success()


@conversation_router.post(
    "/{conversation_id}/switch_llm",
    responses={404: {"description": "Conversation not found"}},
)
async def switch_conversation_llm(
    request: Request,
    conversation_id: UUID,
    llm: LLM = Body(..., embed=True),  # noqa: B008
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """将对话的 LLM 交换为调用者提供的对象。

    由直接拥有 LLM 且不将配置文件推送到智能体服务器的文件系统的应用程序服务器使用（请
    参阅#3017），以及由前端的每个会话模型开关使用，该开关转发配置文件配置，该
    配置文件配置可能通过 id 引用已保存的提供程序连接，而不是携带内联 API 键。
    """
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    conversation = event_service.get_conversation()
    cipher = get_cipher(request)
    if cipher is not None:
        llm = decrypt_incoming_llm_secrets(llm, cipher)
    # 在安装之前，先解决引用的提供者连接 LLM因此，与共享连接关联的配置文件运行在
    # api_key / base_url 而不是一个无密钥的配置 (镜像) LLMProfileStore.load). 一个悬垂的
    # 引用或缺失的引用凭据在工作之前，表面为422 LLM 已被取代。 没有配置文件的 inline-key
    #  配置 provider_connection_id 与旧路径完全相同。
    #
    with store_errors():
        llm = get_llm_profile_store().resolve_provider_connection(llm, cipher=cipher)
    conversation.switch_llm(llm)
    return Success()


@conversation_router.post(
    "/{conversation_id}/load_plugin",
    responses={
        400: {"description": "Invalid plugin reference or inactive conversation"},
        404: {"description": "Conversation or plugin not found"},
    },
)
async def load_conversation_plugin(
    conversation_id: UUID,
    plugin_ref: str = Body(..., embed=True),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """从对话的注册市场加载插件。"""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        await event_service.load_plugin(plugin_ref)
    except (PluginNotFoundError, MarketplaceNotFoundError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except (
        PluginResolutionError,
        PluginFetchError,
        FileNotFoundError,
        ValueError,
    ) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return Success()


@conversation_router.post(
    "/{conversation_id}/switch_acp_model",
    responses={
        400: {"description": "Agent is not ACP, or provider can't switch models"},
        404: {"description": "Conversation not found"},
        504: {"description": "ACP server did not answer the model switch in time"},
    },
)
async def switch_conversation_acp_model(
    conversation_id: UUID,
    model: str = Body(..., embed=True),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """切换 ACP 对话的模型。

    对于已经开始的对话，发出协议级
    ``session/set_model`` 调用 ACP 子进程，因此新模型适用于后续回合而不会丢失上下文。
     对于已创建但尚未运行的会话，该值为已持久化并在第一个会
    话启动时应用（返回
    ``200`` 无论如何）。 仅对提供商支持模型切换的 ACP 对话有效。
    """
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        await event_service.switch_acp_model(model)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except TimeoutError as e:
        # 有界会话/set_model 往返已过期。 ACP 服务器被楔入/缓慢而不是拒绝请求，因此显示
        # 504 而不是不透明的 500。
        #
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(e),
        )
    return Success()


@conversation_router.patch(
    "/{conversation_id}", responses={404: {"description": "Item not found"}}
)
async def update_conversation(
    conversation_id: UUID,
    request: UpdateConversationRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """更新对话元数据。

    此端点允许更新标题等对话详细信息。
    """
    updated = await conversation_service.update_conversation(conversation_id, request)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return Success()


@conversation_router.post(
    "/{conversation_id}/ask_agent",
    responses={404: {"description": "Item not found"}},
)
async def ask_agent(
    conversation_id: UUID,
    request: AskAgentRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> AskAgentResponse:
    """向智能体询问一个简单的问题，而不影响对话状态。"""
    response = await conversation_service.ask_agent(conversation_id, request.question)
    if response is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return AskAgentResponse(response=response)


@conversation_router.post(
    "/{conversation_id}/condense",
    responses={
        404: {"description": "Item not found"},
        409: {"description": "The agent has no condenser that handles requests"},
    },
)
async def condense_conversation(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """强制对话历史记录上下文压缩。"""
    try:
        success = await conversation_service.condense(conversation_id)
    except CondensationUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return Success()


@conversation_router.post(
    "/{conversation_id}/fork",
    responses={
        201: {"description": "Forked conversation created"},
        404: {"description": "Source conversation not found"},
        409: {"description": "Fork ID already in use"},
    },
    status_code=status.HTTP_201_CREATED,
)
async def fork_conversation(
    conversation_id: UUID,
    request: Annotated[ForkConversationRequest, Body()] = ForkConversationRequest(),  # noqa: B008
    include_skills: Annotated[bool, Query(title=INCLUDE_SKILLS_PARAM_TITLE)] = False,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationInfo:
    """分叉对话，深度复制其事件历史记录。

    分叉以 ``idle`` 状态开始，并具有新的事件循环。 在分叉上​​调用 ``run`` 将从复制状
    态恢复，这意味着智能体具有源会话的完整事件内存。
    """
    try:
        info = await conversation_service.fork_conversation(
            conversation_id,
            fork_id=request.id,
            title=request.title,
            tags=request.tags if request.tags is not None else None,
            reset_metrics=request.reset_metrics,
            from_event_id=request.from_event_id,
        )
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        # 未知 ``from_event_id`` 是针对现有源对话的错误请求，而不是丢失的对话。
        #
        if "from_event_id" in str(exc):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise
    if info is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Source conversation not found",
        )
    if not include_skills:
        info = trim_conversation_response_skills(info)
    return info


@conversation_router.post(
    "/{conversation_id}/children",
    responses={
        201: {"description": "Child conversation created"},
        404: {"description": "Parent conversation not found"},
        429: {"description": "Server conversation run capacity is full"},
    },
    status_code=status.HTTP_201_CREATED,
)
async def start_child_conversation(
    conversation_id: UUID,
    request: Annotated[StartChildConversationRequest, Body()],
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> StartChildConversationResponse:
    """在此服务器上启动 ``conversation_id`` 的子对话。

    该子类继承了父类的配置，并工作区（可选地隔离在git工作树中），通过
    ``parent_conversation_id``链接，并以``task``作为其第一个用户消
    息。 这是 ``start_child_conversation`` 工具背后的默认启动器。
    """
    try:
        result = await conversation_service.start_child_conversation(
            conversation_id, request
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Parent conversation not found"
        )
    return result


@conversation_router.post(
    "/{conversation_id}/navigate",
    responses={
        404: {"description": "Conversation or event not found"},
    },
)
async def navigate_conversation(
    conversation_id: UUID,
    request: Annotated[NavigateConversationRequest, Body()],
    include_skills: Annotated[bool, Query(title=INCLUDE_SKILLS_PARAM_TITLE)] = False,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationInfo:
    """将对话的 HEAD 移动到现有事件，重新建立分支。

    所有分支都保留在磁盘上； 仅智能体的活动分支在下一次更改时运行。 与 ``fork`` 不同
    ，不会创建新对话。 返回更新后的对话信息（携带新的
    ``leaf_event_id``）。
    """
    try:
        info = await conversation_service.navigate_conversation(
            conversation_id, event_id=request.event_id
        )
    except ValueError as exc:
        # 针对现有对话的未知 ``event_id`` 是 404； 其他 ValueErrors (e.g.
        # inactive_service) 是真正的服务器错误。
        #
        if "event_id" in str(exc):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise
    if info is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    if not include_skills:
        info = trim_conversation_response_skills(info)
    return info
