import uuid
from unittest.mock import Mock, patch

import httpx
import pytest

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import RemoteWorkspace

from ..conftest import create_mock_http_client


def create_test_agent() -> Agent:
    llm = LLM(model="gpt-4o-mini", api_key=None, usage_id="test-llm")
    return Agent(llm=llm, tools=[])


def test_remote_run_raises_conversation_run_error_with_id():
    agent = create_test_agent()
    conv_id = uuid.uuid4()

    mock_client_instance = create_mock_http_client(conversation_id=str(conv_id))

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
        ),
    ):
        workspace = RemoteWorkspace(
            working_dir="/tmp",
            host="http://localhost:3000",
            api_key=None,
        )

        # 实例化 RemoteConversation 附加到现有 id 以避免创建 POST
        from openhands.sdk.conversation.impl.remote_conversation import (
            RemoteConversation,
        )

        rc = RemoteConversation(
            agent=agent, workspace=workspace, conversation_id=conv_id
        )

        # 修补 _send_request 以针对此对话 ID 在 POST /run 上提出
        def fake_send_request(
            client, method, url, acceptable_status_codes=None, **kwargs
        ):  # noqa: D401, ARG001
            if method == "POST" and str(conv_id) in url and url.endswith("/run"):
                raise httpx.RequestError("boom", request=httpx.Request(method, url))
            # 返回其他调用的最小成功响应
            resp = Mock()
            resp.status_code = 200
            resp.json.return_value = {"items": []}
            resp.raise_for_status.return_value = None
            return resp

        try:
            with patch(
                "openhands.sdk.conversation.impl.remote_conversation._send_request",
                side_effect=fake_send_request,
            ):
                with pytest.raises(ConversationRunError) as excinfo:
                    rc.run()
        finally:
            # 如果需要的话恢复原始（上下文管理器应该处理）
            pass

        err = excinfo.value
        assert getattr(err, "conversation_id", None) == conv_id
        assert str(conv_id) in str(err)
