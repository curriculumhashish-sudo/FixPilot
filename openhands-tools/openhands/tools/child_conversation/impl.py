"""start_child_conversation 工具的执行器。"""

import json
import os
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
from pydantic import ValidationError

from openhands.sdk.conversation.request import (
    StartChildConversationRequest,
    StartChildConversationResponse,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.tool.tool import ToolExecutor
from openhands.tools.child_conversation.definition import (
    StartChildConversationAction,
    StartChildConversationObservation,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation


logger = get_logger(__name__)

# 使用相同的接缝 ``LookupSecret`` 来访问运行此工具的智能体服务器。
INTERNAL_SERVER_URL_ENV = "OH_INTERNAL_SERVER_URL"
DEFAULT_INTERNAL_SERVER_URL = "http://127.0.0.1:8000"
# 由服务器导出的智能体-服务器会话密钥的 v1 和 v0 名称。
SESSION_API_KEY_ENVS = ("OH_SESSION_API_KEYS_0", "SESSION_API_KEY")
SESSION_API_KEY_HEADER = "X-Session-API-Key"
# 启动可能包括工作树或沙箱配置； 镜像 MCP 工具超时而不是 httpx 的 5 秒默认值。
#
CHILD_LAUNCH_TIMEOUT_SECONDS = 300.0


def default_launch_url(parent_conversation_id: UUID) -> str:
    """运行此工具的智能体服务器的子启动端点。"""
    base = os.getenv(INTERNAL_SERVER_URL_ENV, DEFAULT_INTERNAL_SERVER_URL).rstrip("/")
    return f"{base}/api/conversations/{parent_conversation_id}/children"


def session_api_key_headers() -> dict[str, str]:
    """启动器的身份验证标头，取自智能体-服务器自己的环境。

    该密钥向其启动器标识该服务器，就像它对服务器的 Webhook 订阅者所做的那样。
    ``launch_url`` 由谁来决定会话的智能体，而头衔则授予那个派系：一个
    托管后端生成了密钥，而直接发起者必须提供一个来创建会话。
    """
    for env_name in SESSION_API_KEY_ENVS:
        value = os.getenv(env_name)
        if value:
            return {SESSION_API_KEY_HEADER: value}
    return {}


def _response_detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, str) and detail:
        return detail
    if detail is not None:
        return json.dumps(detail)
    return response.text[:500]


class StartChildConversationExecutor(
    ToolExecutor[StartChildConversationAction, StartChildConversationObservation]
):
    """POST 向子启动端点发出启动请求并返回报告。

    执行器故意与后端无关：它只知道电汇合约（``StartChildConversationRequest``中，
    ``StartChildConversationResponse`` out）以及发送到哪里。 默认情况下，它的目标是运
    行此工具的智能体服务器，并使用该服务器自己的
    会话 API 密钥从环境中进行身份验证。
    """

    def __init__(
        self,
        parent_conversation_id: UUID,
        launch_url: str | None = None,
        timeout: float = CHILD_LAUNCH_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ):
        self.parent_conversation_id = parent_conversation_id
        self.launch_url = launch_url
        self.timeout = timeout
        self._transport = transport

    def __call__(
        self,
        action: StartChildConversationAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> StartChildConversationObservation:
        url = self.launch_url or default_launch_url(self.parent_conversation_id)
        try:
            payload = StartChildConversationRequest(
                task=action.task, title=action.title, isolation=action.isolation
            ).model_dump(mode="json")
        except ValidationError as exc:
            return self._error(f"Invalid child conversation request: {exc}")

        try:
            with httpx.Client(
                timeout=self.timeout, transport=self._transport
            ) as client:
                response = client.post(
                    url, json=payload, headers=session_api_key_headers()
                )
            response.raise_for_status()
            result = StartChildConversationResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            return self._error(
                "Child conversation launch failed "
                f"({exc.response.status_code}): {_response_detail(exc.response)}"
            )
        except httpx.TimeoutException:
            return self._error(
                "Child conversation launch timed out after "
                f"{self.timeout:.0f} seconds. The child may still have been "
                "created; check with the user before retrying."
            )
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            logger.warning("start_child_conversation failed against %s: %s", url, exc)
            return self._error(
                f"Child conversation launch failed: {type(exc).__name__}: {exc}"
            )

        summary = (
            f"Started child conversation {result.conversation_id} "
            f"(status: {result.status}).\n"
            f"{json.dumps(result.model_dump(mode='json'), indent=2)}"
        )
        return StartChildConversationObservation.from_text(
            text=summary,
            conversation_id=str(result.conversation_id),
            parent_conversation_id=str(result.parent_conversation_id),
            status=result.status,
            title=result.title,
            url=result.url,
            workspace=result.workspace,
            isolation=result.isolation,
        )

    @staticmethod
    def _error(message: str) -> StartChildConversationObservation:
        return StartChildConversationObservation.from_text(text=message, is_error=True)
