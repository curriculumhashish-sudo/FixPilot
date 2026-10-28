"""测试 RemoteConversation。"""

import time
import uuid
from unittest.mock import Mock, patch

import httpx
import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.agent.acp_agent import ACPAgent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.exceptions import (
    ConversationRunError,
    WebSocketConnectionError,
)
from openhands.sdk.conversation.impl import remote_conversation as remote_module
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.sdk.conversation.request import StartConversationRequest
from openhands.sdk.conversation.secret_registry import SecretValue
from openhands.sdk.conversation.visualizer import DefaultConversationVisualizer
from openhands.sdk.event import Event, MessageEvent, StreamingDeltaEvent
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.conversation_state import (
    FULL_STATE_KEY,
    ConversationStateUpdateEvent,
)
from openhands.sdk.event.llm_completion_log import LLMCompletionLogEvent
from openhands.sdk.hooks import HookConfig
from openhands.sdk.llm import LLM, Message, Metrics, TextContent
from openhands.sdk.llm.streaming import LLMStreamChunk
from openhands.sdk.security.confirmation_policy import AlwaysConfirm
from openhands.sdk.workspace import LocalWorkspace, RemoteWorkspace


class TestRemoteConversation:
    """测试 RemoteConversation 功能。"""

    def setup_method(self):
        """设置测试环境。"""
        self.host: str = "http://localhost:8000"
        self.llm: LLM = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"))
        self.agent: Agent = Agent(llm=self.llm, tools=[])
        self.mock_client: Mock = Mock(spec=httpx.Client)
        self.workspace: RemoteWorkspace = RemoteWorkspace(
            host=self.host, working_dir="/tmp"
        )

    def setup_mock_client(self, conversation_id: str | None = None):
        """使用默认响应为工作区设置模拟对象客户端。"""
        mock_client_instance = Mock()
        self.workspace._client = mock_client_instance

        # 默认对话 ID
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        # 创建默认响应
        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        # 模拟对象返回适当响应的请求方法
        def request_side_effect(method, url, **kwargs):
            if method == "POST" and url == "/api/conversations":
                return mock_conv_response
            elif method == "GET" and "/api/conversations/" in url and "/events" in url:
                return mock_events_response
            elif method == "GET" and url.startswith("/api/conversations/"):
                # 返回带有完成状态的对话信息响应（完成 run() 轮询所需）
                #
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                conv_info = mock_conv_response.json.return_value.copy()
                conv_info["execution_status"] = "finished"
                response.json.return_value = conv_info
                return response
            elif method == "POST" and "/events" in url:
                # POST 至事件端点 (send_message)
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {}
                return response
            elif method == "POST" and "/run" in url:
                # POST 运行端点
                response = Mock()
                response.raise_for_status.return_value = None
                response.status_code = 200
                response.json.return_value = {}
                return response
            elif method == "POST" or method == "PUT":
                # 其他 POST/PUT 请求的默认成功响应
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {}
                return response
            else:
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                return response

        mock_client_instance.request.side_effect = request_side_effect
        return mock_client_instance

    def create_mock_conversation_response(self, conversation_id: str | None = None):
        """创建模拟对象对话创建响应。"""
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "id": conversation_id,
            "conversation_id": conversation_id,
        }
        return mock_response

    def create_mock_events_response(self, events: list | None = None):
        """创建模拟对象事件 API 响应。"""
        if events is None:
            events = []

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "items": events,
            "next_page_id": None,
        }
        return mock_response

    @staticmethod
    def full_state_event(status: str, **values):
        return ConversationStateUpdateEvent(
            key=FULL_STATE_KEY,
            value={"execution_status": status, **values},
        )

    def install_post_run_full_state(
        self,
        mock_client_instance,
        conversation_id: str,
        status: str = "finished",
        **values,
    ):
        """安装一个副作用，在第一个事件上触发全状态 WS 事件
        REST GET 在 POST /run. 之后进行投票

        该事件是从 GET 副作用（在设置 _run_armed 之后，在 _wait_for_run_completion 内
        ）触发的，而不是从 POST 副作用
        触发的。 从 POST 比赛 _run_armed.set() 开火，紧接着 POST 返回，因此该事件将被
         run_complete_callback 的
        武装警卫默默地丢弃。
        """
        ws_callback = [lambda event: None]
        original_side_effect = mock_client_instance.request.side_effect
        fired = [False]

        def custom_side_effect(method, url, **kwargs):
            resp = original_side_effect(method, url, **kwargs)
            if (
                not fired[0]
                and method == "GET"
                and url == f"/api/conversations/{conversation_id}"
            ):
                fired[0] = True
                ws_callback[0](self.full_state_event(status, **values))
            return resp

        mock_client_instance.request.side_effect = custom_side_effect
        return ws_callback

    @pytest.mark.parametrize("kind", ["Agent", "ACPAgent"])
    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_attach_uses_server_agent_without_creating_or_changing_settings(
        self, mock_ws_client, kind
    ):
        cid = uuid.uuid4()
        client = self.setup_mock_client(str(cid))
        original = client.request.side_effect
        expected = self.agent if kind == "Agent" else ACPAgent(acp_command=["test-acp"])

        def respond(method, url, **kwargs):
            response = original(method, url, **kwargs)
            if method == "GET" and url == f"/api/conversations/{cid}":
                response.json.return_value["agent"] = expected.model_dump(mode="json")
                response.json.return_value["max_iterations"] = 500
            return response

        client.request.side_effect = respond
        conversation = RemoteConversation.attach(
            workspace=self.workspace, conversation_id=cid, visualizer=None
        )
        assert type(conversation.agent) is type(expected)
        if kind == "Agent":
            assert conversation.agent.llm.model == expected.llm.model
            assert conversation.agent.tools == expected.tools
        else:
            assert isinstance(conversation.agent, ACPAgent)
            assert isinstance(expected, ACPAgent)
            assert conversation.agent.acp_command == expected.acp_command
        assert conversation.id == cid
        conversation.close()
        assert all(call.args[0] == "GET" for call in client.request.call_args_list)
        client.close.assert_not_called()  # 调用者仍然拥有工作区。

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    @patch(
        "openhands.sdk.conversation.impl.remote_conversation._restore_tool_registrations"
    )
    def test_attach_restores_persisted_tool_modules(
        self, restore_tool_registrations, mock_ws_client
    ):
        mock_ws_client.return_value.wait_until_ready.return_value = True
        cid = uuid.uuid4()
        client = self.setup_mock_client(str(cid))
        original = client.request.side_effect

        def respond(method, url, **kwargs):
            response = original(method, url, **kwargs)
            if method == "GET" and url == f"/api/conversations/{cid}":
                response.json.return_value.update(
                    agent=self.agent.model_dump(mode="json"),
                    max_iterations=500,
                    tool_module_qualnames={
                        "TerminalTool": "openhands.tools.terminal.definition"
                    },
                )
            return response

        client.request.side_effect = respond

        conversation = RemoteConversation.attach(
            workspace=self.workspace, conversation_id=cid, visualizer=None
        )

        restore_tool_registrations.assert_called_once_with(
            {"TerminalTool": "openhands.tools.terminal.definition"}
        )
        conversation.close()

    def test_attach_reports_a_missing_tool_module(self):
        with (
            patch.object(
                remote_module.importlib,
                "import_module",
                side_effect=ModuleNotFoundError("No module named 'optional_tools'"),
            ) as import_module,
            pytest.raises(
                ImportError,
                match=(
                    "Cannot attach to a conversation that uses tool "
                    "'OptionalTool'.*optional_tools.definition"
                ),
            ),
        ):
            remote_module._restore_tool_registrations(
                {"OptionalTool": "optional_tools.definition"}
            )

        import_module.assert_called_once_with("optional_tools.definition")

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    @patch(
        "openhands.sdk.conversation.impl.remote_conversation._restore_tool_registrations"
    )
    def test_constructor_attach_restores_persisted_tool_modules(
        self, restore_tool_registrations, mock_ws_client
    ):
        """``RemoteConversation(conversation_id=...)`` 路径也必须恢复。

        ``Conversation(..., conversation_id=...)`` 在此路由而不是通过 ``attach``
        /``create``，因此跳过恢复将使已持久化工具未注册且其事件不可反序列化。
        """
        mock_ws_client.return_value.wait_until_ready.return_value = True
        cid = uuid.uuid4()
        client = self.setup_mock_client(str(cid))
        original = client.request.side_effect

        def respond(method, url, **kwargs):
            response = original(method, url, **kwargs)
            if method == "GET" and url == f"/api/conversations/{cid}":
                response.json.return_value.update(
                    agent=self.agent.model_dump(mode="json"),
                    max_iterations=500,
                    tool_module_qualnames={
                        "TerminalTool": "openhands.tools.terminal.definition"
                    },
                )
            return response

        client.request.side_effect = respond

        conversation = RemoteConversation(
            agent=self.agent, workspace=self.workspace, conversation_id=cid
        )

        restore_tool_registrations.assert_called_once_with(
            {"TerminalTool": "openhands.tools.terminal.definition"}
        )
        # 附加不得创建对话。
        assert not [
            call
            for call in client.request.call_args_list
            if call.args[0] == "POST" and call.args[1] == "/api/conversations"
        ]
        conversation.close()

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_create_from_profile_uses_resolved_agent(self, mock_ws_client):
        cid, profile_id = uuid.uuid4(), uuid.uuid4()
        hooks = HookConfig.model_validate({"stop": [{"hooks": [{"command": "true"}]}]})
        client = self.setup_mock_client(str(cid))
        original = client.request.side_effect
        created = False

        def respond(method, url, **kwargs):
            nonlocal created
            if method == "GET" and url == f"/api/conversations/{cid}" and not created:
                return httpx.Response(
                    404, request=httpx.Request(method, self.host + url)
                )
            response = original(method, url, **kwargs)
            if method == "POST" and url == "/api/conversations":
                payload = kwargs["json"]
                assert payload["agent_profile_id"] == str(profile_id)
                assert "agent" not in payload and payload["secrets"] == {}
                parsed = StartConversationRequest.model_validate(payload)
                assert parsed.agent_profile_id == profile_id
                assert payload["max_iterations"] == 17
                assert payload["tags"] == {"automationrun": "run-one"}
                assert payload["stuck_detection"] is False
                assert parsed.hook_config == hooks
                assert payload["observability_metadata"] == {"run": "one"}
                assert payload["observability_tags"] == ["automation"]
                assert payload["observability_span_name"] == "scheduled-task"
                assert payload["user_id"] == "operator"
                response.json.return_value["agent"] = self.agent.model_dump(mode="json")
                response.json.return_value["max_iterations"] = 17
                created = True
            return response

        client.request.side_effect = respond
        conversation = RemoteConversation.create(
            workspace=self.workspace,
            request=StartConversationRequest(
                workspace=LocalWorkspace(working_dir=self.workspace.working_dir),
                conversation_id=cid,
                agent_profile_id=profile_id,
                max_iterations=17,
                tags={"automationrun": "run-one"},
                stuck_detection=False,
                hook_config=hooks,
                observability_metadata={"run": "one"},
                observability_tags=["automation"],
                observability_span_name="scheduled-task",
                user_id="operator",
            ),
            visualizer=None,
        )
        assert client.request.call_args_list[0].args == ("POST", "/api/conversations")
        assert conversation.max_iteration_per_run == 17
        assert conversation.id == cid
        assert conversation.agent.llm.model == self.agent.llm.model
        conversation.set_title("Scheduled run")
        assert any(
            c.args == ("PATCH", f"/api/conversations/{cid}")
            and c.kwargs["json"] == {"title": "Scheduled run"}
            for c in client.request.call_args_list
        )
        conversation.close()

    @pytest.mark.parametrize("status", [403, 404])
    @pytest.mark.parametrize("operation", ["attach", "create"])
    def test_failed_explicit_operation_does_not_try_the_other_operation(
        self, status, operation
    ):
        cid = uuid.uuid4()
        client = self.setup_mock_client(str(cid))
        client.request.side_effect = None
        client.request.return_value = httpx.Response(
            status, request=httpx.Request("GET", f"{self.host}/api/conversations/{cid}")
        )
        with pytest.raises(httpx.HTTPStatusError):
            if operation == "attach":
                RemoteConversation.attach(self.workspace, cid, visualizer=None)
            else:
                RemoteConversation.create(
                    self.workspace,
                    StartConversationRequest(
                        agent=self.agent,
                        workspace=LocalWorkspace(working_dir="/tmp"),
                        conversation_id=cid,
                    ),
                    visualizer=None,
                )
        expected_method = "GET" if operation == "attach" else "POST"
        assert [call.args[0] for call in client.request.call_args_list] == [
            expected_method
        ]

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_initialization_new_conversation(self, mock_ws_client):
        """使用新对话测试 RemoteConversation 初始化。"""
        # 设置模拟对象个客户端
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        # 模拟对象 WebSocket 客户端
        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建RemoteConversation
        conversation = RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            max_iteration_per_run=100,
            stuck_detection=True,
        )

        # 验证 WebSocket 客户端已创建并启动
        mock_ws_client.assert_called_once()
        mock_ws_instance.start.assert_called_once()

        # 验证会话属性
        assert conversation.id == uuid.UUID(conversation_id)
        assert conversation.workspace.host == self.host
        assert conversation.max_iteration_per_run == 100

        # 验证 POST 被调用以创建对话
        post_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST" and call[0][1] == "/api/conversations"
        ]
        assert len(post_calls) == 1, (
            "Should have made exactly one POST call to create conversation"
        )

        # 验证 GET 被调用来获取事件（RemoteEventsList 初始化） 这发生在
        # RemoteEventsList._do_full_sync() 中，在 RemoteState 初始化期间调用
        #
        get_events_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "GET" and "/events/search" in call[0][1]
        ]
        assert len(get_events_calls) >= 1, (
            "Should have made at least one GET call to /events/search "
            "to fetch initial events"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_raises_when_websocket_never_ready(
        self, mock_ws_client
    ):
        conversation_id = str(uuid.uuid4())
        self.setup_mock_client(conversation_id=conversation_id)
        mock_ws_instance = Mock()
        mock_ws_instance.wait_until_ready.return_value = False
        mock_ws_client.return_value = mock_ws_instance

        with pytest.raises(WebSocketConnectionError):
            RemoteConversation(agent=self.agent, workspace=self.workspace)

        mock_ws_instance.stop.assert_called_once()

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_can_tolerate_websocket_ready_timeout(
        self, mock_ws_client, monkeypatch
    ):
        conversation_id = str(uuid.uuid4())
        self.setup_mock_client(conversation_id=conversation_id)
        mock_ws_instance = Mock()
        mock_ws_instance.wait_until_ready.return_value = False
        mock_ws_client.return_value = mock_ws_instance
        monkeypatch.setenv("OPENHANDS_REMOTE_WS_READY_REQUIRED", "false")

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        assert conversation.id == uuid.UUID(conversation_id)
        mock_ws_instance.stop.assert_not_called()

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_sends_observability_fields(self, mock_ws_client):
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        mock_ws_client.return_value = Mock()

        RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            observability_metadata={"repo": "OpenHands/software-agent-sdk"},
            observability_tags=["sdk", "remote"],
            observability_span_name="pr_review_evaluation",
            user_id="test-user-42",
        )

        create_call = next(
            (
                call
                for call in mock_client_instance.request.call_args_list
                if call[0][0] == "POST" and call[0][1] == "/api/conversations"
            ),
            None,
        )
        assert create_call is not None, "No POST /api/conversations call found"
        payload = create_call.kwargs["json"]
        assert payload["observability_metadata"] == {
            "repo": "OpenHands/software-agent-sdk"
        }
        assert payload["observability_tags"] == ["sdk", "remote"]
        assert payload["observability_span_name"] == "pr_review_evaluation"
        assert payload["user_id"] == "test-user-42"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_plugin_source_redacted_placeholder_kept(
        self, mock_ws_client
    ):
        """create 载荷屏蔽内联插件源信用但保留 ${VAR}
        占位符，因此服务器通过机密扩展克隆私有插件，而无需原始凭据跨越线路。
        """
        from openhands.sdk.plugin import PluginSource

        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        mock_ws_client.return_value = Mock()

        placeholder = "https://x-token-auth:${MY_TOKEN}@host/org/repo.git"
        RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            plugins=[
                PluginSource(source="https://oauth2:LEAKME@host/org/priv.git"),
                PluginSource(source=placeholder),
            ],
        )

        create_call = next(
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST" and call[0][1] == "/api/conversations"
        )
        sources = [p["source"] for p in create_call.kwargs["json"]["plugins"]]
        assert "https://****@host/org/priv.git" in sources
        assert placeholder in sources
        assert "LEAKME" not in str(create_call.kwargs["json"]["plugins"])

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_user_id_none_sends_explicit_null(self, mock_ws_client):
        """user_id=None sends an explicit null key (not omitted) so the server
        无论是否提供 user_id，都会收到一致的载荷。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        mock_ws_client.return_value = Mock()

        RemoteConversation(agent=self.agent, workspace=self.workspace)

        create_call = next(
            (
                call
                for call in mock_client_instance.request.call_args_list
                if call[0][0] == "POST" and call[0][1] == "/api/conversations"
            ),
            None,
        )
        assert create_call is not None, "No POST /api/conversations call found"
        payload = create_call.kwargs["json"]
        assert "user_id" in payload
        assert payload["user_id"] is None

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_llm_completion_log_callback_writes_utf8(self, mock_ws_client, tmp_path):
        llm = LLM(
            model="gpt-4o-mini",
            api_key=SecretStr("test-key"),
            log_completions=True,
            log_completions_folder=str(tmp_path),
        )
        agent = Agent(llm=llm, tools=[])
        conversation_id = str(uuid.uuid4())
        self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_client.return_value = Mock()
        conversation = RemoteConversation(agent=agent, workspace=self.workspace)
        callback = conversation._create_llm_completion_log_callback()

        real_open = open
        open_calls = []

        def capture_open(*args, **kwargs):
            open_calls.append((args, kwargs))
            return real_open(*args, **kwargs)

        event = LLMCompletionLogEvent(
            filename="completion.json",
            log_data='{"message": "hello 🔐"}',
            usage_id=llm.usage_id,
        )
        with patch("builtins.open", side_effect=capture_open):
            callback(event)

        assert open_calls
        assert open_calls[0][1]["encoding"] == "utf-8"
        assert (tmp_path / "completion.json").read_text(encoding="utf-8") == (
            event.log_data
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_token_callbacks_receive_streamed_deltas(self, mock_ws_client):
        self.setup_mock_client()
        mock_ws_client.return_value = Mock()
        chunks: list[LLMStreamChunk] = []
        events: list[Event] = []

        Conversation(
            agent=self.agent,
            workspace=self.workspace,
            visualizer=None,
            callbacks=[events.append],
            token_callbacks=[chunks.append],
        )
        socket_callback = mock_ws_client.call_args.kwargs["callback"]
        delta = StreamingDeltaEvent(content="Hel", reasoning_content="think")
        socket_callback(delta)
        socket_callback(
            MessageEvent(source="agent", llm_message=Message(role="assistant"))
        )

        assert len(chunks) == 1
        assert chunks[0].choices[0].delta.content == "Hel"
        assert chunks[0].choices[0].delta.reasoning_content == "think"
        assert delta in events

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_acp_remote_conversation_uses_unified_endpoint(self, mock_ws_client):
        acp_agent = ACPAgent(acp_command=["echo", "test"])
        conversation_id = str(uuid.uuid4())
        mock_client_instance = Mock()
        self.workspace._client = mock_client_instance

        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        def request_side_effect(method, url, **kwargs):
            if method == "POST" and url == "/api/conversations":
                return mock_conv_response
            if method == "GET" and "/api/conversations/" in url and "/events" in url:
                return mock_events_response
            if method == "GET" and url.startswith("/api/conversations/"):
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                conv_info = mock_conv_response.json.return_value.copy()
                conv_info["execution_status"] = "finished"
                conv_info["agent"] = {
                    "kind": "ACPAgent",
                    "acp_command": ["echo", "test"],
                }
                response.json.return_value = conv_info
                return response
            response = Mock()
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = {}
            return response

        mock_client_instance.request.side_effect = request_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        RemoteConversation(agent=acp_agent, workspace=self.workspace)

        post_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST" and call[0][1] == "/api/conversations"
        ]
        assert len(post_calls) == 1

        get_events_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "GET" and "/api/conversations/" in call[0][1]
        ]
        assert len(get_events_calls) >= 1

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_initialization_existing_conversation(
        self, mock_ws_client
    ):
        """使用现有对话测试 RemoteConversation 初始化。"""
        # 模拟对象工作区直接客户端
        conversation_id = uuid.uuid4()
        mock_client_instance = self.setup_mock_client(
            conversation_id=str(conversation_id)
        )

        # 模拟对象 WebSocket 客户端
        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 使用现有 ID 创建 RemoteConversation
        conversation = RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            conversation_id=conversation_id,
        )

        # 验证对话 ID 设置正确
        assert conversation.id == conversation_id

        # 验证没有进行 POST 呼叫来创建新对话
        post_create_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST" and call[0][1] == "/api/conversations"
        ]
        assert len(post_create_calls) == 0, (
            "Should not create a new conversation when ID is provided"
        )

        # 验证已拨打 GET 电话以验证现有对话
        get_conversation_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "GET"
            and call[0][1] == f"/api/conversations/{conversation_id}"
        ]
        assert len(get_conversation_calls) == 1, (
            "Should have made exactly one GET call to validate existing conversation"
        )

        # 验证调用 GET 来获取事件（RemoteEventsList 初始化）
        get_events_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "GET" and "/events/search" in call[0][1]
        ]
        assert len(get_events_calls) >= 1, (
            "Should have made at least one GET call to /events/search "
            "to fetch initial events"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_initialization_nonexistent_conversation_creates_new(
        self, mock_ws_client
    ):
        """当 ID 不存在时，测试 RemoteConversation 创建对话。"""
        conversation_id = uuid.uuid4()
        mock_client_instance = Mock()
        self.workspace._client = mock_client_instance

        mock_conv_response = self.create_mock_conversation_response(
            str(conversation_id)
        )
        mock_events_response = self.create_mock_events_response()

        def request_side_effect(method, url, **kwargs):
            # GET 对于特定对话返回 404
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                response = Mock()
                response.status_code = 404
                response.raise_for_status.side_effect = None
                return response
            elif method == "POST" and url == "/api/conversations":
                return mock_conv_response
            elif method == "GET" and "/events/search" in url:
                return mock_events_response
            elif method == "GET" and url.startswith("/api/conversations/"):
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                conv_info = mock_conv_response.json.return_value.copy()
                conv_info["execution_status"] = "finished"
                response.json.return_value = conv_info
                return response
            else:
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {}
                return response

        mock_client_instance.request.side_effect = request_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 使用不存在的 ID 创建 RemoteConversation
        conversation = RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            conversation_id=conversation_id,
        )

        # 验证对话 ID 设置正确
        assert conversation.id == conversation_id

        # 验证已拨打 GET 电话以检查对话是否存在
        get_conversation_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "GET"
            and call[0][1] == f"/api/conversations/{conversation_id}"
        ]
        assert len(get_conversation_calls) == 1, (
            "Should have made exactly one GET call to check if conversation exists"
        )

        # 验证已拨打 POST 电话来创建对话
        post_create_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST" and call[0][1] == "/api/conversations"
        ]
        assert len(post_create_calls) == 1, (
            "Should have made exactly one POST call to create the conversation"
        )

        # 验证 POST 载荷包含 conversation_id
        post_call = post_create_calls[0]
        payload = post_call[1].get("json", {})
        assert payload.get("conversation_id") == str(conversation_id), (
            "POST payload should contain the specified conversation_id"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_existing_different_agent_kind_raises_clear_error(
        self, mock_ws_client
    ):
        conversation_id = uuid.uuid4()
        mock_client_instance = Mock()
        self.workspace._client = mock_client_instance

        def request_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "id": str(conversation_id),
                    "execution_status": "idle",
                    "agent": {
                        "kind": "ACPAgent",
                        "acp_command": ["echo", "test"],
                    },
                }
                return response
            response = Mock()
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = {}
            return response

        mock_client_instance.request.side_effect = request_side_effect

        with pytest.raises(ValueError, match="different agent kind"):
            RemoteConversation(
                agent=self.agent,
                workspace=self.workspace,
                conversation_id=conversation_id,
            )

        mock_ws_client.assert_not_called()
        post_create_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
        ]
        assert post_create_calls == []

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_send_message_string(self, mock_ws_client):
        """测试发送字符串消息。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并发送消息
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.send_message("Hello, world!")

        # 验证已进行消息 API 调用（确切的载荷结构可能会有所不同） 检查是否已对事件端点进
        # 行了 POST
        #
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/events" in call[0][1]
        ]
        assert len(request_calls) >= 1, (
            "Should have made a POST call to events endpoint"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_send_message_object(self, mock_ws_client):
        """测试发送 Message 对象。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并发送消息
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        message = Message(
            role="user",
            content=[TextContent(text="Hello from message object!")],
        )
        conversation.send_message(message)

        # 验证已进行消息 API 调用（确切的载荷结构可能会有所不同） 检查是否已对事件端点进
        # 行了 POST
        #
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/events" in call[0][1]
        ]
        assert len(request_calls) >= 1, (
            "Should have made a POST call to events endpoint"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_send_message_invalid_role(self, mock_ws_client):
        """测试发送具有无效角色的消息会引发断言错误。"""
        # 设置模拟对象
        mock_client_instance = self.setup_mock_client()

        conversation_id = str(uuid.uuid4())
        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        mock_client_instance.post.return_value = mock_conv_response
        mock_client_instance.get.return_value = mock_events_response

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        # 尝试发送角色无效的消息
        invalid_message = Message(
            role="assistant",  # 仅允许“用户”角色
            content=[TextContent(text="Invalid role message")],
        )

        with pytest.raises(AssertionError, match="Only user messages are allowed"):
            conversation.send_message(invalid_message)

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.generate_conversation_title"
    )
    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_generate_title_reconciles_locally(
        self, mock_ws_client, mock_generate_title
    ):
        """generate_title 使用协调的本地事件而不是 REST 端点。"""
        conversation_id = str(uuid.uuid4())
        user_event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="Hello from remote title")]
            ),
        )
        synced_events: list[dict] = []

        mock_client_instance = Mock()
        self.workspace._client = mock_client_instance
        mock_conv_response = self.create_mock_conversation_response(conversation_id)

        def request_side_effect(method, url, **kwargs):
            if method == "POST" and url == "/api/conversations":
                return mock_conv_response
            if (
                method == "GET"
                and "/api/conversations/" in url
                and "/events/search" in url
            ):
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "items": list(synced_events),
                    "next_page_id": None,
                }
                return response
            if method == "GET" and url.startswith("/api/conversations/"):
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                conv_info = mock_conv_response.json.return_value.copy()
                conv_info["execution_status"] = "finished"
                response.json.return_value = conv_info
                return response
            if method == "POST" and url.endswith("/events"):
                synced_events[:] = [user_event.model_dump(mode="json")]
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {}
                return response
            response = Mock()
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = {}
            return response

        mock_client_instance.request.side_effect = request_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance
        mock_generate_title.return_value = "Remote title"

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.send_message("Hello from remote title")

        title = conversation.generate_title(max_length=60)

        assert title == "Remote title"
        mock_generate_title.assert_called_once()
        call_kwargs = mock_generate_title.call_args.kwargs
        assert call_kwargs["llm"] == self.agent.llm
        assert call_kwargs["max_length"] == 60
        reconciled_events = list(call_kwargs["events"])
        assert len(reconciled_events) == 1
        assert (
            reconciled_events[0].llm_message.content[0].text
            == "Hello from remote title"
        )
        assert not any(
            call[0][0] == "POST" and call[0][1].endswith("/generate_title")
            for call in mock_client_instance.request.call_args_list
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run(self, mock_ws_client):
        """测试运行对话。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        ws_callback = self.install_post_run_full_state(
            mock_client_instance, conversation_id
        )

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并运行
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]
        conversation.run()

        # 验证 run API 调用
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/run" in call[0][1]
        ]
        assert len(request_calls) >= 1, "Should have made a POST call to run endpoint"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_already_running(self, mock_ws_client):
        """当对话已经运行时测试运行（409 响应）。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        ws_callback = [lambda event: None]

        # 覆盖默认请求 side_effect，为 /run 端点返回 409。 全状态完成事件在第一个 GET 轮
        # 询（启动后）上触发，而不是与 POST 内联，因为 _run_armed 是在 POST 返回后设置的
        # 。
        #
        original_side_effect = mock_client_instance.request.side_effect
        fired = [False]

        def custom_side_effect(method, url, **kwargs):
            if method == "POST" and "/run" in url:
                mock_run_response = Mock()
                mock_run_response.status_code = 409  # 已经运行
                mock_run_response.raise_for_status.return_value = None
                return mock_run_response
            resp = original_side_effect(method, url, **kwargs)
            if (
                not fired[0]
                and method == "GET"
                and url == f"/api/conversations/{conversation_id}"
            ):
                fired[0] = True
                ws_callback[0](self.full_state_event("finished"))
            return resp

        mock_client_instance.request.side_effect = custom_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并运行
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]
        # 当blocking=True（默认）时，它将轮询直到完成
        conversation.run()  # 不应引发异常

        # 验证已进行 run API 调用
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/run" in call[0][1]
        ]
        assert len(request_calls) >= 1, "Should have made a POST call to run endpoint"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_non_blocking(self, mock_ws_client):
        """测试运行带有blocking=False 的对话会立即返回。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并以阻塞=False运行
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.run(blocking=False)

        # 验证已进行 run API 调用
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/run" in call[0][1]
        ]
        assert len(request_calls) == 1, "Should have made exactly one POST call"

        # 验证未进行任何轮询 GET 调用（仅获取初始事件）
        get_conversation_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "GET"
            and call[0][1] == f"/api/conversations/{conversation_id}"
        ]
        # 应为 0，因为blocking=False 会跳过轮询
        assert len(get_conversation_calls) == 0, (
            "Should not poll for status when blocking=False"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_blocking_polls_until_finished(
        self, mock_ws_client
    ):
        """测试blocking=True是否等待运行后状态快照。

        RESTFINISHED只是一个健康信号； 服务器的完整状态ConversationStateUpdateEvent是
        权威的运行完成信号。
        """
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        # 跟踪民意调查计数并为前 2 个民意调查返回“正在运行”，然后返回“已完成”
        poll_count = [0]
        original_side_effect = mock_client_instance.request.side_effect
        ws_callback = [lambda event: None]

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                poll_count[0] += 1
                response = Mock()
                response.raise_for_status.return_value = None
                if poll_count[0] <= 2:
                    response.json.return_value = {
                        "id": conversation_id,
                        "execution_status": "running",
                    }
                else:
                    response.json.return_value = {
                        "id": conversation_id,
                        "execution_status": "finished",
                    }
                    if poll_count[0] == 5:
                        ws_callback[0](self.full_state_event("finished"))
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并以阻塞=True运行
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]
        conversation.run(blocking=True, poll_interval=0.01)  # 快速轮询测试

        # 单独验证RESTFINISHED没有完成运行； 仅在交付运行后完整状态快照后，运行才会返回
        # 。
        #
        assert poll_count[0] == 5, (
            f"Should have polled until the post-run snapshot arrived, got "
            f"{poll_count[0]} poll(s)"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_returns_on_waiting_for_confirmation_snapshot(
        self, mock_ws_client
    ):
        """运行后非运行全状态快照完成阻塞run()。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        ws_callback = [lambda event: None]
        original_side_effect = mock_client_instance.request.side_effect
        first_poll = [True]

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                if first_poll[0]:
                    # 在第一个 REST 轮询上触发全状态事件，该轮询在设置 _run_armed 后在
                    # _wait_for_run_completion() 内运行。
                    #
                    first_poll[0] = False
                    ws_callback[0](self.full_state_event("waiting_for_confirmation"))
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "id": conversation_id,
                    "execution_status": "waiting_for_confirmation",
                    "stats": {"usage_to_metrics": {}},
                }
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect
        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]

        conversation.run(blocking=True, poll_interval=0.01)

        assert conversation.state.execution_status.value == "waiting_for_confirmation"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_preserves_post_run_snapshot_after_running_poll(
        self, mock_ws_client
    ):
        """进行中的 RUNNING REST 轮询不得丢弃运行后快照。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        ws_callback = [lambda event: None]
        poll_count = [0]
        original_side_effect = mock_client_instance.request.side_effect

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                poll_count[0] += 1
                ws_callback[0](self.full_state_event("finished"))
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "id": conversation_id,
                    "execution_status": "running",
                    "stats": {"usage_to_metrics": {}},
                }
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect
        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]

        conversation.run(blocking=True, poll_interval=0.01, timeout=0.1)

        assert poll_count[0] == 1

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_ws_finished_is_only_a_hint_not_terminal(
        self, mock_ws_client
    ):
        """WS 交付的 FINISHED 状态必须不自行终止 ``run()``。

        回归测试我们在重试-16 中观察到的 stop-hook 竞赛（运行 25497962453，对话
        dd86d184…，agourlay/zip-passw
        ord-finder）：

        单个 ``LocalConversation.run`` 循环内的服务器端时间线：
          1. ``agent.step()``套``execution_status = FINISHED``； 该状态更新事件通过
          WebSocket 广播。
          2. **锁在迭代结束时释放**。 客户端通过 WS 观察 FINISHED。
          3. 下一个循环迭代获取锁，运行停止钩子，钩子返回rc=2，状态恢复为RUNNING，
          ``continue``。

        在旧的实现中，步骤 2 导致客户端
        ``_wait_for_run_completion`` to ``return`` 立即在 WS-delivered 上 FINISHED —
        按照服务器
        钩子的评估和拆除智能体-server pod (via ``workspace_keepalive`` 在之前智能体它
        可以消耗其迭代预算。

        修复：每个字段 WS FINISHED 在完成时被忽略。 只有运行后的完整状态快照才是权威
        的。
        """
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        # REST 轮询脚本：前 3 个轮询显示服务器已翻转
        # *back* 到 RUNNING（停止钩子恢复）； 随后的民意调查显示
        # 智能体的第二次完成，应该受到尊重。
        rest_script = [
            "running",
            "running",
            "running",
            "finished",
            "finished",
            "finished",
            "finished",
        ]
        poll_count = [0]
        original_side_effect = mock_client_instance.request.side_effect
        ws_callback = [lambda event: None]

        def custom_side_effect(method, url, **kwargs):
            if method == "POST" and url == f"/api/conversations/{conversation_id}/run":
                response = original_side_effect(method, url, **kwargs)
                ws_callback[0](
                    ConversationStateUpdateEvent(
                        key="execution_status", value="finished"
                    )
                )
                return response
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                idx = min(poll_count[0], len(rest_script) - 1)
                status = rest_script[idx]
                poll_count[0] += 1
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "id": conversation_id,
                    "execution_status": status,
                    "stats": {"usage_to_metrics": {}},
                }
                if poll_count[0] >= len(rest_script):
                    ws_callback[0](self.full_state_event("finished"))
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect
        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]

        conversation.run(blocking=True, poll_interval=0.01)

        # 必须轮询超过 3 RUNNING REST 响应（竞争窗口），然后等待运行后完整状态快照。 预
        # 先修复此问题将在 /run 触发器之后注入的 WS FINISHED 上返回，其中 poll_count ==
        # 0。
        #
        assert poll_count[0] == len(rest_script), (
            f"Run() returned before the post-run snapshot. poll_count={poll_count[0]}"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_rest_finished_revert_waits_for_full_state(
        self, mock_ws_client
    ):
        """当钩子仍然可以否决它时，不要从 REST FINISHED 返回。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        rest_script = [
            "finished",
            "finished",
            "finished",
            "running",
            "running",
            "finished",
            "finished",
            "finished",
            "finished",
        ]
        poll_count = [0]
        original_side_effect = mock_client_instance.request.side_effect

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                idx = min(poll_count[0], len(rest_script) - 1)
                status = rest_script[idx]
                poll_count[0] += 1
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "id": conversation_id,
                    "execution_status": status,
                    "stats": {"usage_to_metrics": {}},
                }
                if poll_count[0] >= len(rest_script):
                    ws_callback[0](self.full_state_event("finished"))
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect
        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance
        ws_callback = [lambda event: None]

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]

        conversation.run(blocking=True, poll_interval=0.01)

        assert poll_count[0] >= len(rest_script), (
            f"Run() returned before the post-run full-state snapshot. "
            f"poll_count={poll_count[0]}"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_ws_error_still_terminates_immediately(
        self, mock_ws_client
    ):
        """ERROR 通过 WS 仍然会立即引发（不受钩子恢复的影响）。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_client.return_value = Mock()
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        error = ConversationErrorEvent(
            source="environment",
            code="LLMAuthenticationError",
            detail="invalid api key",
        )
        ws_callback = mock_ws_client.call_args.kwargs["callback"]

        original_side_effect = mock_client_instance.request.side_effect

        def post_run_seeds_error(method, url, **kwargs):
            resp = original_side_effect(method, url, **kwargs)
            if method == "POST" and url.endswith("/run"):
                conversation.state.events.add_event(error)
                ws_callback(
                    ConversationStateUpdateEvent(key="execution_status", value="error")
                )
            return resp

        mock_client_instance.request.side_effect = post_run_seeds_error

        with pytest.raises(ConversationRunError) as excinfo:
            conversation.run(blocking=True, poll_interval=10.0)

        attached = excinfo.value.conversation_error
        assert attached is not None
        assert attached is error
        classification = attached.classification
        assert classification is not None
        assert classification.kind == "auth"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_stale_pre_run_snapshot_is_ignored(
        self, mock_ws_client
    ):
        """在 run() POST 之前收到的全状态 WS 快照不得完成 run()。

        WS 订阅在以下期间发送初始完整状态快照：
        connect(). If that snapshot carries a non-RUNNING status (e.g. "idle"),
        它必须不被视为运行后完成信号 _run_armed 尚未在此处设置。 run() 只有在全量状态
        快照到达后才应完成 POST  /run call.
        """
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        ws_callback = [lambda event: None]
        original_side_effect = mock_client_instance.request.side_effect
        poll_count = [0]

        def custom_side_effect(method, url, **kwargs):
            resp = original_side_effect(method, url, **kwargs)
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                poll_count[0] += 1
                if poll_count[0] == 1:
                    # 在第一次REST轮次（已武装）时，执行真实后的快照。
                    ws_callback[0](self.full_state_event("finished"))
            return resp

        mock_client_instance.request.side_effect = custom_side_effect
        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]

        # 在调用 run() 之前，将过时的“空闲”快照直接注入队列，就好像它来自初始订阅一样。
        # _run_armed 尚未设置，因此 run_complete_callback 会丢弃它，但模拟直接队列放置可
        # 以让我们验证守卫端到端的工作情况。
        #
        ws_callback[0](self.full_state_event("idle"))
        assert conversation._terminal_status_queue.empty(), (
            "Stale pre-run snapshot must not enter the queue (_run_armed not set)"
        )

        # run() 应通过第一个 REST 轮询的完整状态事件完成，而不是过时的预运行快照。
        #
        conversation.run(blocking=True, poll_interval=0.01)
        assert poll_count[0] >= 1

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_rest_hard_fallback_when_ws_silent(
        self, mock_ws_client
    ):
        """当 WS 快照从未到达时，run() 通过 REST 硬回退方案完成。

        当运行后 WS 全状态快照从未交付时 (e.g. 运行完成后套接字被丢弃），客户端不应该
        挂起直到整体超时。 在连续 REST 个终端轮询
        TERMINAL_HARD_FALLBACK_SECS 后，它必须接受状态并返回。

        time.monotonic 被修补为每次调用提前 10 秒，因此在 ~3 REST 轮询后超过 30 秒阈
        值（实际挂墙时间 ~poll_interval
        * 3）。
        """
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)
        poll_count = [0]
        original_side_effect = mock_client_instance.request.side_effect

        def custom_side_effect(method, url, **kwargs):
            resp = original_side_effect(method, url, **kwargs)
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                poll_count[0] += 1
                # 切勿触发运行后 WS 快照 — 模拟静默套接字。
            return resp

        mock_client_instance.request.side_effect = custom_side_effect
        mock_ws_client.return_value = Mock()

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        # 修补 time.monotonic 以将每次调用提前 10 秒，以便在 ~3 REST 轮询后跨越 30 秒硬
        # 回退方案阈值。
        #
        call_counter = [0]
        base = time.monotonic()

        def fast_monotonic() -> float:
            call_counter[0] += 1
            return base + call_counter[0] * 10.0

        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.time.monotonic",
            side_effect=fast_monotonic,
        ):
            conversation.run(blocking=True, poll_interval=0.01)

        assert poll_count[0] >= 1, f"Expected at least 1 REST poll, got {poll_count[0]}"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_full_state_updates_cached_state(
        self, mock_ws_client
    ):
        """运行后全状态快照会在 run() 返回之前更新缓存状态。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        stale_info = {
            "id": conversation_id,
            "execution_status": "finished",
            "stats": {"usage_to_metrics": {}},
        }
        final_info = {
            "id": conversation_id,
            "execution_status": "finished",
            "stats": {
                "usage_to_metrics": {
                    "test-llm": {
                        "model_name": "gpt-4o-mini",
                        "accumulated_cost": 1.25,
                        "accumulated_token_usage": {
                            "model": "gpt-4o-mini",
                            "prompt_tokens": 120,
                            "completion_tokens": 30,
                            "cache_read_tokens": 0,
                            "cache_write_tokens": 0,
                            "reasoning_tokens": 0,
                            "context_window": 200000,
                            "per_turn_token": 150,
                            "response_id": "",
                        },
                    }
                }
            },
        }

        poll_count = [0]
        original_side_effect = mock_client_instance.request.side_effect
        ws_callback = [lambda event: None]

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                poll_count[0] += 1
                response = Mock()
                response.status_code = 200
                response.raise_for_status.return_value = None
                if poll_count[0] <= 2:
                    response.json.return_value = {
                        "id": conversation_id,
                        "execution_status": "running",
                        "stats": {"usage_to_metrics": {}},
                    }
                elif poll_count[0] <= 4:
                    response.json.return_value = stale_info
                else:
                    response.json.return_value = final_info
                    ws_callback[0](
                        ConversationStateUpdateEvent(
                            key=FULL_STATE_KEY,
                            value=final_info,
                        )
                    )
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        ws_callback[0] = mock_ws_client.call_args.kwargs["callback"]
        conversation.state._cached_state = {
            "id": conversation_id,
            "execution_status": "running",
            "stats": {"usage_to_metrics": {}},
        }

        conversation.run(blocking=True, poll_interval=0.01)

        assert poll_count[0] >= 1
        assert "test-llm" in conversation.state.stats.usage_to_metrics
        assert conversation.state.stats.usage_to_metrics[
            "test-llm"
        ].accumulated_cost == pytest.approx(1.25)

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_error_status_raises(self, mock_ws_client):
        """测试错误状态是否升高 ConversationRunError。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        original_side_effect = mock_client_instance.request.side_effect

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                response = Mock()
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "id": conversation_id,
                    "execution_status": "error",
                }
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        with pytest.raises(ConversationRunError) as exc_info:
            conversation.run(poll_interval=0.01)
        assert "error" in str(exc_info.value).lower()

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_stuck_status_raises(self, mock_ws_client):
        """测试卡住状态是否升高 ConversationRunError。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        original_side_effect = mock_client_instance.request.side_effect

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                response = Mock()
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "id": conversation_id,
                    "execution_status": "stuck",
                }
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        with pytest.raises(ConversationRunError) as exc_info:
            conversation.run(poll_interval=0.01)
        assert "stuck" in str(exc_info.value).lower()

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_404_raises(self, mock_ws_client):
        """测试轮询期间 404 是否引发 ConversationRunError。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        original_side_effect = mock_client_instance.request.side_effect

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                request = httpx.Request("GET", f"http://localhost{url}")
                return httpx.Response(404, request=request, text="Not Found")
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        with pytest.raises(ConversationRunError) as exc_info:
            conversation.run(poll_interval=0.01)
        assert "not found" in str(exc_info.value).lower()

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_run_timeout(self, mock_ws_client):
        """测试 run() 在超时上引发 ConversationRunError。"""
        from openhands.sdk.conversation.exceptions import ConversationRunError

        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        # 始终返回“运行”状态以触发超时
        original_side_effect = mock_client_instance.request.side_effect

        def custom_side_effect(method, url, **kwargs):
            if method == "GET" and url == f"/api/conversations/{conversation_id}":
                response = Mock()
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "id": conversation_id,
                    "execution_status": "running",
                }
                return response
            return original_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = custom_side_effect

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并以非常短的超时运行
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        with pytest.raises(ConversationRunError) as exc_info:
            conversation.run(blocking=True, poll_interval=0.01, timeout=0.05)

        # 验证错误包含超时信息
        assert "timed out" in str(exc_info.value).lower()

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_set_confirmation_policy(self, mock_ws_client):
        """测试设置确认策略。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并设置策略
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        policy = AlwaysConfirm()
        conversation.set_confirmation_policy(policy)

        # 验证策略 API 调用
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/confirmation_policy"
            in call[0][1]
        ]
        assert len(request_calls) >= 1, (
            "Should have made a POST call to confirmation_policy endpoint"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_reject_pending_actions(self, mock_ws_client):
        """测试拒绝待处理的操作。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并拒绝操作
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.reject_pending_actions("Custom rejection reason")

        # 验证拒绝 API 通话
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/events/respond_to_confirmation"
            in call[0][1]
        ]
        assert len(request_calls) >= 1, (
            "Should have made a POST call to respond_to_confirmation endpoint"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_pause(self, mock_ws_client):
        """暂停对话。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并暂停
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.pause()

        # 验证暂停 API 通话
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/pause" in call[0][1]
        ]
        assert len(request_calls) >= 1, "Should have made a POST call to pause endpoint"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_interrupt(self, mock_ws_client):
        """interrupt() 必须 POST 到 /interrupt，而不是降级到 /pause."""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.interrupt()

        posts = [
            call[0][1]
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
        ]
        assert any(
            f"/api/conversations/{conversation_id}/interrupt" in url for url in posts
        ), "Should have made a POST call to interrupt endpoint"
        assert not any(
            f"/api/conversations/{conversation_id}/pause" in url for url in posts
        ), "interrupt() must not degrade to the pause endpoint"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_load_plugin(self, mock_ws_client):
        """load_plugin () POSTs 插件引用服务器。"""
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.load_plugin("review-bot@team")

        matching_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/load_plugin" in call[0][1]
        ]
        assert len(matching_calls) == 1
        assert matching_calls[0].kwargs["json"] == {"plugin_ref": "review-bot@team"}

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_update_secrets(self, mock_ws_client):
        """测试更新机密。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并更新机密
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        # 使用字符串机密进行测试
        from typing import cast

        from openhands.sdk.conversation.secret_registry import SecretValue

        secrets = cast(
            dict[str, SecretValue],
            {
                "api_key": "secret_value",
                "token": "another_secret",
            },
        )
        conversation.update_secrets(secrets)

        # 验证机密 API 通话
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/secrets" in call[0][1]
        ]
        assert len(request_calls) >= 1, (
            "Should have made a POST call to secrets endpoint"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_update_secrets_callable(self, mock_ws_client):
        """测试更新机密的可调用值。"""
        # 设置模拟对象
        conversation_id = str(uuid.uuid4())
        mock_client_instance = self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并使用可调用更新机密
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        def get_secret():
            return "callable_secret_value"

        secrets: dict[str, SecretValue] = {
            "api_key": "string_secret",
            "callable_secret": get_secret,  # type: ignore[dict-item]
        }
        conversation.update_secrets(secrets)

        # 验证机密 API 调用已解析的可调用对象
        request_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "POST"
            and f"/api/conversations/{conversation_id}/secrets" in call[0][1]
        ]
        assert len(request_calls) >= 1, (
            "Should have made a POST call to secrets endpoint"
        )

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_close(self, mock_ws_client):
        """测试关闭对话。"""
        # 设置模拟对象
        mock_client_instance = self.setup_mock_client()

        conversation_id = str(uuid.uuid4())
        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        mock_client_instance.post.return_value = mock_conv_response
        mock_client_instance.get.return_value = mock_events_response

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话并结束
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.close()

        # 验证 WebSocket 客户端已停止
        mock_ws_instance.stop.assert_called_once()

        # 验证 HTTP 客户端已不关闭，因为它与工作区共享。 工作区拥有该客户端，并将在其自
        # 己的清理过程中关闭它。
        #
        mock_client_instance.close.assert_not_called()

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_close_reports_accumulated_cost_to_workspace(self, mock_ws_client):
        """平仓将累积的 LLM 成本变为工作区。"""
        self.setup_mock_client()
        mock_ws_client.return_value = Mock()
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        metrics = Metrics(model_name="gpt-4o-mini")
        metrics.add_cost(0.75)
        stats = ConversationStats(usage_to_metrics={"agent": metrics})
        conversation.state.update_state_from_event(
            self.full_state_event("finished", stats=stats.model_dump(mode="json"))
        )

        conversation.close()

        assert self.workspace.accumulated_cost == 0.75

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_close_does_not_fetch_state_to_read_cost(self, mock_ws_client):
        """关闭永远不会获取超过 HTTP 的状态——服务器可能已经消失了。"""
        mock_client_instance = self.setup_mock_client()
        mock_ws_client.return_value = Mock()
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        mock_client_instance.request.reset_mock()

        conversation.close()

        assert mock_client_instance.request.call_args_list == []

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_close_leaves_cost_unreported_when_state_has_no_stats(self, mock_ws_client):
        """未知成本保持未报告状态，而不是报告为 0.0。"""
        self.setup_mock_client()
        mock_ws_client.return_value = Mock()
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)
        conversation.state.update_state_from_event(
            ConversationStateUpdateEvent(key="execution_status", value="finished")
        )

        conversation.close()

        assert self.workspace.accumulated_cost is None

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_close_reports_streamed_cost_on_error_only_wakeup(self, mock_ws_client):
        """故障路径报告本次运行的支出，而不是订阅快照。

        ERROR/STUCK 从每个字段的更新中唤醒 run()，因此 close() 在服务器的运行后全状态
        快照落地之前运行。 成本仍然是正确的，因为 Agen
        t Server 在每次 LLM 响应 (EventService._setup_stats_streaming) 后都会流式传输
        “统计”更新。
        """
        self.setup_mock_client()
        mock_ws_client.return_value = Mock()
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        # 订阅时全状态快照：统计信息存在，但成本仍为 0。
        conversation.state.update_state_from_event(
            self.full_state_event(
                "running", stats=ConversationStats().model_dump(mode="json")
            )
        )
        # 服务器在运行的 LLM 响应后流式传输统计信息。
        metrics = Metrics(model_name="gpt-4o-mini")
        metrics.add_cost(0.75)
        conversation.state.update_state_from_event(
            ConversationStateUpdateEvent(
                key="stats",
                value=ConversationStats(usage_to_metrics={"agent": metrics}),
            )
        )
        # 运行失败：只有每个字段的状态更新在 close() 之前到达。
        conversation.state.update_state_from_event(
            ConversationStateUpdateEvent(key="execution_status", value="error")
        )

        conversation.close()

        assert self.workspace.accumulated_cost == 0.75

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_cleanup_lifecycle_flags(self, mock_ws_client):
        """RemoteConversation 清理更新声明的生命周期标志。

        验证 close() 更新标志并且是幂等的。
        """
        conversation_id = uuid.uuid4()
        self.setup_mock_client(str(conversation_id))

        conversation = RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            conversation_id=conversation_id,
        )
        assert conversation.cleanup_initiated is False
        assert conversation.cleanup_complete is False

        conversation.close()
        assert conversation.cleanup_initiated is True
        assert conversation.cleanup_complete is True

        # close() is idempotent
        conversation.close()
        assert conversation.cleanup_complete is True

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_stuck_detector_not_implemented(self, mock_ws_client):
        """测试 stuck_detector 属性是否引发 NotImplementedError。"""
        # 设置模拟对象
        mock_client_instance = self.setup_mock_client()

        conversation_id = str(uuid.uuid4())
        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        mock_client_instance.post.return_value = mock_conv_response
        mock_client_instance.get.return_value = mock_events_response

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        # 访问 stuck_detector 应该引发 NotImplementedError
        with pytest.raises(
            NotImplementedError, match="stuck detection is not available"
        ):
            _ = conversation.stuck_detector

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_with_callbacks(self, mock_ws_client):
        """使用自定义回调测试 RemoteConversation。"""
        # 设置模拟对象
        mock_client_instance = self.setup_mock_client()

        conversation_id = str(uuid.uuid4())
        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        mock_client_instance.post.return_value = mock_conv_response
        mock_client_instance.get.return_value = mock_events_response

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建自定义回调
        callback_calls = []

        def custom_callback(event):
            callback_calls.append(event)

        # 与回调创建对话
        _conversation = RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            callbacks=[custom_callback],
        )

        # 验证 WebSocket 客户端是使用回调创建的回调应该是包含自定义回调的组合回调
        #
        mock_ws_client.assert_called_once()
        call_args = mock_ws_client.call_args
        assert "callback" in call_args[1]  # 应该有一个回调参数

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_with_visualize(self, mock_ws_client):
        """使用 Visualizer=DefaultConversationVisualizer() 测试 RemoteConversation。"""
        # 设置模拟对象
        mock_client_instance = self.setup_mock_client()

        conversation_id = str(uuid.uuid4())
        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        mock_client_instance.post.return_value = mock_conv_response
        mock_client_instance.get.return_value = mock_events_response

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建自定义可视化工具实例
        custom_visualizer = DefaultConversationVisualizer()

        # 使用 Visualizer=DefaultConversationVisualizer() 创建对话
        conversation = RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            visualizer=custom_visualizer,
        )

        # 验证是否直接使用自定义可视化工具实例
        assert conversation._visualizer is custom_visualizer

        # 验证可视化工具的 on_event 回调是否在回调列表中
        assert custom_visualizer.on_event in conversation._callbacks

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_host_url_normalization(self, mock_ws_client):
        """测试主机 URL 是否已正确标准化。"""
        # 设置模拟对象
        mock_client_instance = self.setup_mock_client()

        conversation_id = str(uuid.uuid4())
        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        mock_client_instance.post.return_value = mock_conv_response
        mock_client_instance.get.return_value = mock_events_response

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 使用尾部斜杠进行测试
        host_with_slash = "http://localhost:8000/"
        workspace_with_slash = RemoteWorkspace(host=host_with_slash, working_dir="/tmp")
        workspace_with_slash._client = mock_client_instance
        conversation = RemoteConversation(
            agent=self.agent, workspace=workspace_with_slash
        )

        # 验证尾部斜杠已删除且工作区主机已标准化
        assert conversation.workspace.host == "http://localhost:8000"

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_execute_tool_not_implemented(self, mock_ws_client):
        """测试 execute_tool 为 RemoteConversation 引发 NotImplementedError。"""
        # 设置模拟对象
        mock_client_instance = self.setup_mock_client()

        conversation_id = str(uuid.uuid4())
        mock_conv_response = self.create_mock_conversation_response(conversation_id)
        mock_events_response = self.create_mock_events_response()

        mock_client_instance.post.return_value = mock_conv_response
        mock_client_instance.get.return_value = mock_events_response

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 创建对话
        conversation = RemoteConversation(agent=self.agent, workspace=self.workspace)

        # 创建一个虚拟动作（使用简单的模拟对象）
        from unittest.mock import MagicMock

        mock_action = MagicMock()

        # 验证 execute_tool 加注 NotImplementedError
        with pytest.raises(NotImplementedError) as exc_info:
            conversation.execute_tool("any_tool", mock_action)

        assert "not yet supported for RemoteConversation" in str(exc_info.value)

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_remote_conversation_calls_register_conversation(self, mock_ws_client):
        """测试 RemoteConversation.__init__ 调用 workspace.register_conversation。"""
        conversation_id = str(uuid.uuid4())
        self.setup_mock_client(conversation_id=conversation_id)

        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 在类级别修补 register_conversation 以验证它是否被调用
        with patch.object(RemoteWorkspace, "register_conversation") as mock_register:
            # 创建 RemoteConversation - 这应该调用 register_conversation
            _conversation = RemoteConversation(
                agent=self.agent,
                workspace=self.workspace,
            )

            # 验证使用对话 ID 调用 register_conversation
            mock_register.assert_called_once_with(conversation_id)

    @patch(
        "openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient"
    )
    def test_reconnect_replays_missed_events_to_callbacks_once(self, mock_ws_client):
        """套接字关闭时存储的事件在重新连接时达到回调。"""

        def user_message(text: str) -> MessageEvent:
            return MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text=text)]),
            )

        history = user_message("history")
        live = user_message("live")
        missed_1 = user_message("missed 1")
        missed_2 = user_message("missed 2")
        after = user_message("after")
        server_events = [history]

        mock_client_instance = self.setup_mock_client()
        default_side_effect = mock_client_instance.request.side_effect

        def request_side_effect(method, url, **kwargs):
            if method == "GET" and url.endswith("/events/search"):
                return self.create_mock_events_response(
                    [event.model_dump(mode="json") for event in server_events]
                )
            return default_side_effect(method, url, **kwargs)

        mock_client_instance.request.side_effect = request_side_effect
        mock_ws_client.return_value = Mock()
        seen: list[str] = []

        conversation = RemoteConversation(
            agent=self.agent,
            workspace=self.workspace,
            callbacks=[
                lambda e: seen.append(e.id) if isinstance(e, MessageEvent) else None
            ],
        )
        ws_callback = mock_ws_client.call_args.kwargs["callback"]
        on_reconnect = mock_ws_client.call_args.kwargs["on_reconnect"]

        server_events.append(live)
        ws_callback(live)
        # 插座掉落； 服务器记录了两个无人直播的事件。
        server_events.extend([missed_1, missed_2])

        on_reconnect()
        # 新订阅可能仍会传送重播所涵盖的事件。
        ws_callback(missed_2)
        server_events.append(after)
        ws_callback(after)

        assert seen == [live.id, missed_1.id, missed_2.id, after.id]
        assert [e.id for e in conversation.state.events] == [
            history.id,
            live.id,
            missed_1.id,
            missed_2.id,
            after.id,
        ]
