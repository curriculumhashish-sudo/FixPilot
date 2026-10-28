"""使用真实的 FastAPI Agent Server 和修补的 LLM 进行端到端测试。

这将根据实际的 REST + WebSocket 端点验证 RemoteConversation，
while keeping the LLM deterministic via monkeypatching.
"""

import json
import os
import shutil
import sys
import tempfile
import textwrap
import threading
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
import uvicorn
from fastapi import WebSocket
from filelock import FileLock
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse
from openai.types.responses import ResponseInputItemParam
from pydantic import SecretStr
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from openhands.agent_server.__main__ import preload_modules
from openhands.agent_server.config import load_config
from openhands.sdk import LLM, Agent, AgentContext, Conversation, Message, TextContent
from openhands.sdk.conversation import RemoteConversation
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    CondensationSummaryEvent,
    ConversationStateUpdateEvent,
    Event,
    HookExecutionEvent,
    LLMConvertibleEvent,
    MessageEvent,
    ObservationEvent,
    PauseEvent,
    SystemPromptEvent,
)
from openhands.sdk.git.exceptions import GitCommandError
from openhands.sdk.git.utils import run_git_command
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
from openhands.sdk.skills import Skill
from openhands.sdk.subagent import AgentDefinition
from openhands.sdk.subagent.registry import (
    _reset_registry_for_tests,
    get_factory_info,
    get_registered_agent_definitions,
    register_agent,
    register_agent_if_absent,
)
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE
from openhands.sdk.workspace import RemoteWorkspace
from openhands.workspace.docker.workspace import find_available_tcp_port


@contextmanager
def live_server_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    import_modules: str | None = None,
    session_api_keys: list[str] | None = None,
    deferred_init: bool = False,
    config_overrides: dict[str, object] | None = None,
) -> Generator[dict]:
    """启动由临时工作区和对话支持的真实 FastAPI 服务器。

    我们在创建应用程序之前设置 OPENHANDS_AGENT_SERVER_CONFIG_PATH，以便路由器选择正确
    的默认配置和内存服务。
    """

    # 创建一个指向 tmp 目录的独立配置
    conversations_path = tmp_path / "conversations"
    workspace_path = tmp_path / "workspace"

    # 确保干净的目录（tmp 和 cwd 中的任何剩余目录） 清理当前工作目录中先前运行的任何剩余
    # 目录
    #
    cwd_conversations = Path("workspace/conversations")
    if cwd_conversations.exists():
        shutil.rmtree(cwd_conversations)

    # 为了安全起见，还要完全清理工作区目录
    cwd_workspace = Path("workspace")
    if cwd_workspace.exists():
        # 仅删除对话子目录以避免干扰其他测试
        for item in cwd_workspace.iterdir():
            if item.name == "conversations":
                shutil.rmtree(item)

    # 清理tmp目录
    if conversations_path.exists():
        shutil.rmtree(conversations_path)
    if workspace_path.exists():
        shutil.rmtree(workspace_path)

    conversations_path.mkdir(parents=True, exist_ok=True)
    workspace_path.mkdir(parents=True, exist_ok=True)

    # 验证对话目录确实为空
    assert not list(conversations_path.iterdir()), (
        f"Conversations path not empty: {list(conversations_path.iterdir())}"
    )

    cfg: dict[str, object] = {
        "session_api_keys": session_api_keys or [],
        "conversations_path": str(conversations_path),
        "workspace_path": str(workspace_path),
        "bash_events_dir": str(tmp_path / "bash-events"),
    }
    if deferred_init:
        cfg.update(deferred_init=True, secret_key="test-bootstrap-key")
    cfg.update(config_overrides or {})
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg))

    # 确保默认配置使用我们的文件并禁用任何环境密钥覆盖
    monkeypatch.setenv("OPENHANDS_AGENT_SERVER_CONFIG_PATH", str(cfg_file))
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / ".openhands"))
    monkeypatch.delenv("OH_CONVERSATIONS_PATH", raising=False)
    monkeypatch.delenv("SESSION_API_KEY", raising=False)
    monkeypatch.delenv("OH_SESSION_API_KEYS_0", raising=False)
    monkeypatch.delenv("TMUX_TMPDIR", raising=False)

    if import_modules is not None:
        preload_modules(import_modules)

    # 设置 env 后构建应用程序
    from openhands.agent_server.api import create_app
    from openhands.agent_server.config import Config
    from openhands.agent_server.persistence import reset_stores

    reset_stores()
    cfg_obj = Config.model_validate_json(cfg_file.read_text())

    app = create_app(cfg_obj)

    # 在自由端口上启动 uvicorn
    port = find_available_tcp_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", ws="wsproto"
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # 等待服务器准备好进行健康检查

    base_url = f"http://127.0.0.1:{port}"
    server_ready = False
    for attempt in range(50):  # 等待最多5秒
        try:
            with httpx.Client() as client:
                response = client.get(f"{base_url}/health", timeout=2.0)
                if response.status_code == 200:
                    server_ready = True
                    break
        except (httpx.RequestError, httpx.TimeoutException):
            pass
        time.sleep(0.1)

    if not server_ready:
        raise RuntimeError("Server failed to start within timeout")

    try:
        yield {
            "app": app,
            "conversation_service": (
                None if deferred_init else app.state.conversation_service
            ),
            "host": f"http://127.0.0.1:{port}",
            "workspace_path": workspace_path,
        }
    finally:
        # uvicorn.Server 此处缺乏强大的关闭功能 API； 依赖守护进程线程退出。
        server.should_exit = True
        thread.join(timeout=2)

        # 清理测试期间创建的所有剩余目录
        cwd_conversations = Path("workspace/conversations")
        if cwd_conversations.exists():
            shutil.rmtree(cwd_conversations)
        reset_stores()


def _assert_secret(value: "str | SecretStr", expected: str) -> None:
    """断言 SecretStr-或-str api_key 与预期的明文匹配。"""
    if isinstance(value, SecretStr):
        assert value.get_secret_value() == expected
    else:
        assert value == expected


def test_deferred_websocket_initialization_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def accept_app_backend_websocket(
        websocket: WebSocket, _extension_name: str, _path: str
    ) -> None:
        await websocket.accept()
        await websocket.close()

    monkeypatch.setattr(
        "openhands.agent_server.canvas_extensions_bridge_router."
        "proxy_app_backend_websocket",
        accept_app_backend_websocket,
    )

    with live_server_env(tmp_path, monkeypatch, deferred_init=True) as environment:
        host = environment["host"]
        websocket_origin = host.replace("http://", "ws://")
        bash_socket_url = f"{websocket_origin}/sockets/bash-events"
        app_backend_socket_urls = (
            f"{websocket_origin}/app-backends/test-extension",
            f"{websocket_origin}/app-backends/test-extension/events",
        )

        with httpx.Client(base_url=host, trust_env=False) as client:
            assert client.get("/api/init").json()["state"] == "dormant"
            assert client.get("/api/conversations/count").status_code == 503

            for socket_url in (*app_backend_socket_urls, bash_socket_url):
                with pytest.raises(InvalidStatus) as rejected:
                    with connect(socket_url):
                        pytest.fail(f"Dormant WebSocket accepted: {socket_url}")
                assert rejected.value.response.status_code == 403

            initialized = client.post(
                "/api/init",
                headers={"X-Init-API-Key": "test-bootstrap-key"},
                json={"session_api_keys": ["test-ready-key"]},
            )
            assert initialized.status_code == 200
            assert initialized.json()["state"] == "ready"
            assert client.get("/api/conversations/count").status_code == 401
            assert (
                client.get(
                    "/api/conversations/count",
                    headers={"X-Session-API-Key": "test-ready-key"},
                ).status_code
                == 200
            )

            for socket_url in app_backend_socket_urls:
                with connect(socket_url):
                    pass

            with connect(bash_socket_url) as websocket:
                websocket.send(json.dumps({"type": "auth", "session_api_key": "wrong"}))
                with pytest.raises(ConnectionClosed) as unauthorized:
                    websocket.recv(timeout=5)
                assert unauthorized.value.rcvd is not None
                assert unauthorized.value.rcvd.code == 4001

            with connect(bash_socket_url) as websocket:
                websocket.send(
                    json.dumps({"type": "auth", "session_api_key": "test-ready-key"})
                )
                websocket.send(
                    json.dumps({"command": "printf websocket-ready", "timeout": 5})
                )
                output = ""
                while True:
                    event = json.loads(websocket.recv(timeout=10))
                    if event["kind"] == "BashOutput":
                        output += event.get("stdout") or ""
                        if event["exit_code"] is not None:
                            assert event["exit_code"] == 0
                            break
                assert output == "websocket-ready"


@pytest.mark.parametrize(
    ("stored_key", "previous_keys"),
    [
        ("test-old-key", ["test-old-key"]),
        ("test-current-key", []),
    ],
    ids=["rotated-key", "current-key"],
)
def test_deferred_init_refreshes_persistence_ciphers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stored_key: str,
    previous_keys: list[str],
):
    with live_server_env(
        tmp_path, monkeypatch, config_overrides={"secret_key": stored_key}
    ) as environment:
        with httpx.Client(base_url=environment["host"], trust_env=False) as client:
            assert (
                client.patch(
                    "/api/settings",
                    json={"agent_settings_diff": {"llm": {"api_key": "sk-test-saved"}}},
                ).status_code
                == 200
            )
            assert (
                client.put(
                    "/api/settings/secrets",
                    json={"name": "QA_TOKEN", "value": "test-saved-secret"},
                ).status_code
                == 200
            )

    with live_server_env(
        tmp_path,
        monkeypatch,
        deferred_init=True,
        config_overrides={
            "telemetry": {
                "exporter": "http",
                "http_endpoint": "http://127.0.0.1:9",
            },
        },
    ) as environment:
        with httpx.Client(base_url=environment["host"], trust_env=False) as client:
            response = client.post(
                "/api/init",
                headers={"X-Init-API-Key": "test-bootstrap-key"},
                json={
                    "secret_key": "test-current-key",
                    "previous_secret_keys": previous_keys,
                },
            )
            assert response.status_code == 200
            settings = client.get(
                "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
            ).json()
            assert settings["llm_api_key_is_set"] is True
            assert settings["agent_settings"]["llm"]["api_key"] == "sk-test-saved"
            assert client.get("/api/settings/secrets/QA_TOKEN").text == (
                "test-saved-secret"
            )

            persistence_dir = tmp_path / ".openhands"
            cipher = Cipher("test-current-key")
            saved_settings = json.loads((persistence_dir / "settings.json").read_text())
            saved_secrets = json.loads((persistence_dir / "secrets.json").read_text())
            assert (
                cipher.try_decrypt_str(
                    saved_settings["agent_settings"]["llm"]["api_key"]
                )
                == "sk-test-saved"
            )
            assert (
                cipher.try_decrypt_str(
                    saved_secrets["custom_secrets"]["QA_TOKEN"]["secret"]
                )
                == "test-saved-secret"
            )

            assert (
                client.patch(
                    "/api/settings", json={"misc_settings_diff": {"qa_note": True}}
                ).status_code
                == 200
            )
            assert (
                client.put(
                    "/api/settings/secrets", json={"name": "QA_OTHER", "value": "x"}
                ).status_code
                == 200
            )


def test_health_endpoints_return_ok_json(server_env):
    with httpx.Client() as client:
        for endpoint in ("/alive", "/health"):
            response = client.get(f"{server_env['host']}{endpoint}", timeout=1.0)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}


@pytest.mark.skipif(os.name != "posix", reason="tmux requires Unix sockets")
def test_live_server_does_not_use_inherited_tmux_namespace(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="oh-host-tmux-", dir="/tmp") as shared:
        monkeypatch.setenv("TMUX_TMPDIR", shared)
        with live_server_env(tmp_path, monkeypatch):
            socket_root = os.environ.get("TMUX_TMPDIR")
            assert socket_root != shared
            assert socket_root is not None and Path(socket_root).is_dir()


def test_live_server_does_not_use_inherited_session_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OH_SESSION_API_KEYS_0", "host-session-key")
    with live_server_env(tmp_path, monkeypatch):
        assert "OH_SESSION_API_KEYS_0" not in os.environ


def test_live_server_uses_configured_conversations_path(tmp_path, monkeypatch):
    monkeypatch.setenv("OH_CONVERSATIONS_PATH", str(tmp_path / "host-conversations"))
    with live_server_env(tmp_path, monkeypatch):
        assert load_config().conversations_path == tmp_path / "conversations"


def test_prepare_for_sandbox_pause_drains_conversations(server_env):
    agent = Agent(
        llm=LLM(model="gpt-4o-mini", api_key=SecretStr("test")),
        tools=[],
    )
    payload = {
        "agent": agent.model_dump(mode="json", context={"expose_secrets": True}),
        "workspace": {"working_dir": "/tmp/workspace/project"},
    }
    with httpx.Client(base_url=server_env["host"]) as client:
        start = client.post("/api/conversations", json=payload, timeout=10.0)
        start.raise_for_status()
        conversation_id = UUID(start.json()["id"])
        assert conversation_id in server_env["conversation_service"]._event_services

        response = client.post(
            "/api/conversations/prepare-for-sandbox-pause",
            timeout=10.0,
        )

    assert response.status_code == 204
    assert conversation_id not in server_env["conversation_service"]._event_services
    assert conversation_id in server_env["conversation_service"]._conversation_records


@pytest.fixture
def server_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[dict]:
    with live_server_env(tmp_path, monkeypatch) as env:
        yield env


@pytest.fixture
def authenticated_server_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[dict]:
    api_key = "test-websocket-auth-key"
    with live_server_env(
        tmp_path,
        monkeypatch,
        session_api_keys=[api_key],
    ) as env:
        env["api_key"] = api_key
        yield env


@pytest.fixture
def patched_llm(monkeypatch: pytest.MonkeyPatch) -> list[list[Message]]:
    """修补 LLM.completion 以确定性助理消息响应。"""

    calls: list[list[Message]] = []

    def fake_completion(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        from openhands.sdk.llm.llm_response import LLMResponse

        calls.append(messages)

        # 使用一条辅助消息创建最小的 ModelResponse
        litellm_msg = LiteLLMMessage.model_validate(
            {
                "role": "assistant",
                "content": "Hello from patched LLM",
            }
        )
        raw_response = ModelResponse(
            id="test-resp",
            created=int(time.time()),
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
        )

        # 转换为 OpenHands 消息
        message = Message.from_llm_chat_message(litellm_msg)

        self.metrics.add_token_usage(
            prompt_tokens=7,
            completion_tokens=5,
            cache_read_tokens=0,
            cache_write_tokens=0,
            context_window=8192,
            response_id="test-resp",
            reasoning_tokens=0,
        )

        # 返回 LLMResponse，符合智能体的预期
        return LLMResponse(
            message=message,
            metrics=self.metrics.get_snapshot(),
            raw_response=raw_response,
        )

    monkeypatch.setattr(LLM, "completion", fake_completion, raising=True)

    async def fake_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        return fake_completion(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", fake_acompletion, raising=True)
    return calls


def test_child_launch_in_fresh_workspace_preserves_unborn_repository(
    server_env, patched_llm
):
    workspace = server_env["workspace_path"] / "fresh-parent"
    workspace.mkdir()
    original_file = workspace / "parent.txt"
    original_file.write_text("uncommitted parent work\n")
    with httpx.Client(base_url=server_env["host"], timeout=30) as client:
        parent_response = client.post(
            "/api/conversations",
            json={
                "agent": {
                    "llm": {"model": "gpt-4o-mini", "api_key": "test"},
                    "tools": [],
                },
                "workspace": {"working_dir": str(workspace)},
                "autotitle": False,
            },
        )
        assert parent_response.status_code == 201
        parent_id = parent_response.json()["id"]
        assert (workspace / ".git").is_dir()
        status_before = run_git_command(["git", "status", "--porcelain"], workspace)
        head_before = run_git_command(["git", "symbolic-ref", "HEAD"], workspace)

        response = client.post(
            f"/api/conversations/{parent_id}/children",
            json={"task": "Reply with ok."},
        )
        assert response.status_code == 201, response.text
        child = response.json()
        assert child["isolation"] == "shared"
        assert child["workspace"] == str(workspace)
        child_id = child["conversation_id"]
        deadline = time.monotonic() + 10
        while True:
            child_info = client.get(f"/api/conversations/{child_id}").json()
            if child_info["execution_status"] == "finished":
                break
            assert time.monotonic() < deadline, child_info["execution_status"]
            time.sleep(0.05)
        assert child_info["parent_conversation_id"] == parent_id
        parent = client.get(f"/api/conversations/{parent_id}").json()
        assert parent["sub_conversation_ids"] == [child_id]
        assert (
            run_git_command(["git", "symbolic-ref", "HEAD"], workspace) == head_before
        )
        assert (
            run_git_command(["git", "status", "--porcelain"], workspace)
            == status_before
        )
        with pytest.raises(GitCommandError):
            run_git_command(["git", "rev-parse", "--verify", "HEAD"], workspace)
        assert original_file.read_text() == "uncommitted parent work\n"
        assert (
            len(run_git_command(["git", "worktree", "list"], workspace).splitlines())
            == 1
        )
        assert client.delete(f"/api/conversations/{child_id}").status_code == 200
        assert client.delete(f"/api/conversations/{parent_id}").status_code == 200


def test_remote_conversation_websocket_first_message_auth(
    authenticated_server_env,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OPENHANDS_REMOTE_WS_READY_TIMEOUT", "2")
    agent = Agent(
        llm=LLM(model="gpt-4o-mini", api_key=SecretStr("test")),
        tools=[],
    )
    workspace = RemoteWorkspace(
        host=authenticated_server_env["host"],
        working_dir="/tmp/workspace/project",
        api_key=authenticated_server_env["api_key"],
    )

    conversation: RemoteConversation = Conversation(agent=agent, workspace=workspace)
    try:
        assert conversation.id
    finally:
        conversation.close()


def test_preloaded_custom_tool_resolves_in_live_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """在实时对话创建期间可以使用启动预加载的工具。"""
    from openhands.sdk.tool import Tool, registry as tool_registry

    package_name = "preload_live_server_tools_2771"
    module_qualname = f"{package_name}.tools"
    package_dir = tmp_path / package_name
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    (package_dir / "tools.py").write_text(
        textwrap.dedent(
            """\
            from __future__ import annotations

            from collections.abc import Sequence
            from typing import ClassVar

            from openhands.sdk.tool import (
                Action,
                Observation,
                ToolDefinition,
                ToolExecutor,
                register_tool,
            )


            class PreloadedAction(Action):
                pass


            class PreloadedObservation(Observation):
                pass


            class PreloadedExecutor(
                ToolExecutor[PreloadedAction, PreloadedObservation]
            ):
                def __call__(
                    self,
                    action: PreloadedAction,
                    conversation=None,
                ) -> PreloadedObservation:
                    return PreloadedObservation.from_text("preloaded")


            class PreloadedLiveServerTool(
                ToolDefinition[PreloadedAction, PreloadedObservation]
            ):
                name: ClassVar[str] = "preloaded_live_server_tool"

                @classmethod
                def create(
                    cls, conv_state=None, **params
                ) -> Sequence[PreloadedLiveServerTool]:
                    return [
                        cls(
                            description="Tool registered by startup preload.",
                            action_type=PreloadedAction,
                            observation_type=PreloadedObservation,
                            executor=PreloadedExecutor(),
                        )
                    ]


            register_tool(PreloadedLiveServerTool.name, PreloadedLiveServerTool)
            """
        )
    )

    registry_snapshot = dict(tool_registry._REG)
    usability_snapshot = dict(tool_registry._USABILITY_REG)
    tool_class_snapshot = dict(tool_registry._TOOL_CLASSES)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(package_name, None)
    sys.modules.pop(module_qualname, None)

    try:
        with live_server_env(
            tmp_path, monkeypatch, import_modules=module_qualname
        ) as env:
            llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
            agent = Agent(
                llm=llm,
                tools=[Tool(name="preloaded_live_server_tool")],
                include_default_tools=[],
            )
            payload = {
                "agent": agent.model_dump(
                    mode="json", context={"expose_secrets": True}
                ),
                "workspace": {"working_dir": "/tmp/workspace/project"},
                "initial_message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Initialize tools."}],
                },
                "tool_module_qualnames": {},
            }

            with httpx.Client(base_url=env["host"]) as client:
                response = client.post("/api/conversations", json=payload, timeout=10)

            assert response.status_code == 201, response.text
            conversation_id = UUID(response.json()["id"])
            event_service = env["conversation_service"]._event_services[conversation_id]
            assert event_service._conversation is not None
            assert (
                "preloaded_live_server_tool"
                in event_service._conversation.agent.tools_map
            )
    finally:
        sys.modules.pop(package_name, None)
        sys.modules.pop(module_qualname, None)
        tool_registry._REG.clear()
        tool_registry._REG.update(registry_snapshot)
        tool_registry._USABILITY_REG.clear()
        tool_registry._USABILITY_REG.update(usability_snapshot)
        tool_registry._TOOL_CLASSES.clear()
        tool_registry._TOOL_CLASSES.update(tool_class_snapshot)


def test_websocket_attach_wait_does_not_block_ready_endpoint(server_env):
    """被阻止的 WebSocket 快照不得停止活动服务器事件循环。

    此练习模拟生产形状的失败模式，进行真实对话的端到端测试同步 state 锁启动第二个
    RemoteConversation 该端点附着到同一个服务器端会话，并验证
    `/ready` 仍然响应 WebSocket 订阅正在等待其初始锁定状态快照。
    """
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[])
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(agent=agent, workspace=workspace)
    conversation_id = conv.id

    event_service = server_env["conversation_service"]._event_services[conversation_id]
    assert event_service is not None
    assert event_service._conversation is not None

    attach_error: list[BaseException] = []
    attach_result: dict[str, RemoteConversation] = {}
    attach_thread = None
    lock_thread = None
    lock_acquired = threading.Event()
    release_state_lock = threading.Event()
    snapshot_started = threading.Event()
    conversation_info_started = threading.Event()
    original_snapshot = event_service._create_state_update_event_sync

    from openhands.agent_server import (
        conversation_service as conversation_service_module,
    )

    original_compose_info_sync = (
        conversation_service_module._compose_conversation_info_sync
    )

    def traced_snapshot() -> ConversationStateUpdateEvent:
        snapshot_started.set()
        return original_snapshot()

    def traced_compose_info_sync(*args, **kwargs):
        conversation_info_started.set()
        return original_compose_info_sync(*args, **kwargs)

    def hold_state_lock() -> None:
        assert event_service._conversation is not None
        with event_service._conversation._state:
            lock_acquired.set()
            release_state_lock.wait(timeout=5.0)

    def attach_conversation() -> None:
        attach_workspace = RemoteWorkspace(
            host=server_env["host"], working_dir="/tmp/workspace/project"
        )
        try:
            attach_result["conversation"] = Conversation(
                agent=agent,
                workspace=attach_workspace,
                conversation_id=conversation_id,
            )
        except BaseException as exc:  # pragma: no cover - surfaced by assertions
            attach_error.append(exc)

    event_service._create_state_update_event_sync = traced_snapshot
    conversation_service_module._compose_conversation_info_sync = (
        traced_compose_info_sync
    )

    try:
        lock_thread = threading.Thread(target=hold_state_lock, daemon=True)
        lock_thread.start()
        assert lock_acquired.wait(timeout=2.0), (
            "Failed to acquire the conversation state lock for the live-server "
            "reproduction"
        )

        attach_thread = threading.Thread(target=attach_conversation, daemon=True)
        attach_thread.start()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not (
            conversation_info_started.is_set() or snapshot_started.is_set()
        ):
            time.sleep(0.01)
        assert conversation_info_started.is_set() or snapshot_started.is_set(), (
            "The conversation attach never reached a state snapshot"
        )
        assert attach_thread.is_alive(), (
            "Expected conversation attach to still be waiting on the state lock"
        )

        ready_started = time.monotonic()
        with httpx.Client() as client:
            ready_response = client.get(f"{server_env['host']}/ready", timeout=1.0)
        ready_elapsed = time.monotonic() - ready_started

        assert ready_response.status_code == 200
        assert ready_response.json() == {"status": "ready"}
        assert ready_elapsed < 0.5, (
            f"/ready took {ready_elapsed:.3f}s while conversation attach was waiting "
            "for the conversation state lock"
        )
    finally:
        event_service._create_state_update_event_sync = original_snapshot
        conversation_service_module._compose_conversation_info_sync = (
            original_compose_info_sync
        )
        release_state_lock.set()
        if lock_thread is not None:
            lock_thread.join(timeout=2.0)
        if attach_thread is not None:
            attach_thread.join(timeout=10.0)
        attached_conv = attach_result.get("conversation")
        if attached_conv is not None:
            attached_conv.close()
        conv.close()

    assert not attach_error, (
        f"Attaching to the existing conversation failed: {attach_error[0]}"
    )
    assert attach_thread is not None
    assert not attach_thread.is_alive(), "Websocket attach never finished"
    attached_conv = attach_result.get("conversation")
    assert attached_conv is not None
    assert attached_conv.id == conversation_id


def test_remote_conversation_over_real_server(server_env, patched_llm):
    import shutil
    from pathlib import Path

    # 使用真实的 LLM 对象创建智能体（针对确定性进行修补）
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[])

    # 通过指向实时服务器的工厂创建对话
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(
        agent=agent, workspace=workspace
    )  # RemoteConversation

    # 无需 Docker 后端即可进行生命周期检查/重新配置。
    runtime_url = f"{server_env['host']}/api/conversations/{conv.id}/runtime"
    with httpx.Client() as client:
        before = client.get(runtime_url)
        before.raise_for_status()
        assert before.json() == {
            "runtime_status": "available",
            "can_resume": True,
            "runtime_error": None,
        }
        after = client.post(runtime_url + "/reprovision")
        after.raise_for_status()
        assert after.json() == before.json()

    # 发送消息并运行
    conv.send_message("Say hello")
    conv.run()

    # 验证状态转换以及我们收到一条助理消息
    state = conv.state
    assert state.execution_status.value in {"finished", "idle", "running"}

    # 等待 WS 传递的事件并使用正确的类型检查验证它们
    found_state_update = False
    found_agent_event = False

    for i in range(50):  # 长达〜5秒
        events = state.events

        # 使用 isinstance 检查验证事件类型（不是 hasattr/getattr）
        for e in events:
            assert isinstance(
                e,
                (
                    MessageEvent,
                    ActionEvent,
                    ObservationEvent,
                    AgentErrorEvent,
                    Event,
                    LLMConvertibleEvent,
                    SystemPromptEvent,
                    PauseEvent,
                    CondensationSummaryEvent,
                    ConversationStateUpdateEvent,
                ),
            ), f"Unexpected event type: {type(e).__name__}"

        # 通过正确的 isinstance 检查来检查预期的事件类型
        for e in events:
            if isinstance(e, SystemPromptEvent) and e.source == "agent":
                found_agent_event = True

            if isinstance(e, ConversationStateUpdateEvent):
                found_state_update = True
                # 验证它具有预期的结构
                assert e.source == "environment", (
                    "ConversationStateUpdateEvent should have source='environment'"
                )

            # 找到后验证 MessageEvent 结构
            if isinstance(e, MessageEvent) and e.source == "agent":
                assert hasattr(e, "llm_message"), (
                    "MessageEvent should have llm_message attribute"
                )
                assert e.llm_message.role in ("assistant", "user"), (
                    f"Expected role to be assistant or user, got {e.llm_message.role}"
                )
                found_agent_event = True

            # 找到后验证 ActionEvent 结构
            if isinstance(e, ActionEvent) and e.source == "agent":
                assert hasattr(e, "tool_name"), (
                    "ActionEvent should have tool_name attribute"
                )
                found_agent_event = True

        # 我们检查与智能体相关的事件和状态更新。
        # 注意：由于比赛，SystemPromptEvent 可能无法通过 WebSocket 交付
        # 在 WebSocket 订阅完成之前发布事件的情况。 事件在服务器上已持久化，但
        # RemoteEventsList 可能会错过它。 参见：
        # https://github.com/OpenHands/software-agent-sdk/issues/1785
        #
        if found_agent_event and found_state_update:
            break
        time.sleep(0.1)

    # 断言我们得到了带有描述性消息的预期事件
    assert found_state_update, (
        f"Expected to find ConversationStateUpdateEvent. "
        f"Found {len(state.events)} events: {[type(e).__name__ for e in state.events]}"
    )
    assert found_agent_event, (
        "Expected to find an agent event "
        "(SystemPromptEvent, MessageEvent, or ActionEvent). "
        f"Found {len(state.events)} events: {
            [
                (
                    type(e).__name__,
                    e.source
                    if isinstance(
                        e,
                        (
                            MessageEvent,
                            ActionEvent,
                            SystemPromptEvent,
                            ConversationStateUpdateEvent,
                        ),
                    )
                    else 'N/A',
                )
                for e in state.events
            ]
        }"
    )

    conv.close()

    # 清理可能在 cwd 中创建的所有对话目录
    cwd_conversations = Path("workspace/conversations")
    if cwd_conversations.exists():
        shutil.rmtree(cwd_conversations)


@pytest.mark.parametrize(
    "tags", [None, {"purpose": "debugging"}, {"title": "user tag"}]
)
def test_remote_fork_title_stays_out_of_tags(server_env, tags: dict[str, str] | None):
    agent = Agent(llm=LLM(model="gpt-4o-mini", usage_id="test"), tools=[])
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir=str(server_env["workspace_path"])
    )
    source = Conversation(agent=agent, workspace=workspace, tags={"source": "original"})
    expected_tags = tags or {}
    assert isinstance(source, RemoteConversation)
    try:
        fork = source.fork(title="Debug investigation", tags=tags)
        try:
            response = httpx.get(f"{server_env['host']}/api/conversations/{fork.id}")
            response.raise_for_status()
            assert response.json()["title"] == "Debug investigation"
            assert response.json()["tags"] == expected_tags

            pause = httpx.post(
                f"{server_env['host']}/api/conversations/prepare-for-sandbox-pause"
            )
            pause.raise_for_status()
            state_file = (
                server_env["conversation_service"].conversations_dir
                / fork.id.hex
                / "base_state.json"
            )
            assert json.loads(state_file.read_text())["tags"] == expected_tags
            metadata_file = state_file.with_name("meta.json")
            assert json.loads(metadata_file.read_text())["tags"] == expected_tags
            reloaded = httpx.get(f"{server_env['host']}/api/conversations/{fork.id}")
            reloaded.raise_for_status()
            assert reloaded.json()["title"] == "Debug investigation"
            assert reloaded.json()["tags"] == expected_tags
        finally:
            fork.close()
    finally:
        source.close()


def test_remote_conversation_created_from_agent_settings(server_env):
    from openhands.sdk.conversation.request import StartConversationRequest
    from openhands.sdk.workspace import LocalWorkspace

    working_dir = str(server_env["workspace_path"])
    conversation = RemoteConversation.create(
        RemoteWorkspace(host=server_env["host"], working_dir=working_dir),
        StartConversationRequest(
            agent_settings={
                "agent_kind": "openhands",
                "llm": {"model": "settings-model", "api_key": "sk-settings"},
                "tools": [],
            },
            workspace=LocalWorkspace(working_dir=working_dir),
        ),
        visualizer=None,
    )

    assert conversation.agent.llm.model == "settings-model"
    conversation.close()


def test_openai_chat_completions_gateway_over_real_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patched_llm
):
    from openhands.agent_server import (
        config as config_module,
        conversation_service as service_module,
    )
    from openhands.sdk.llm.llm_profile_store import LLMProfileStore

    monkeypatch.setattr(config_module, "_default_config", None)
    monkeypatch.setattr(service_module, "_conversation_service", None)
    monkeypatch.delenv("OH_WEBHOOKS_0_BASE_URL", raising=False)

    profiles_dir = tmp_path / "profiles"
    store = LLMProfileStore(base_dir=profiles_dir)
    store.save(
        "smoke",
        LLM(model="gpt-4o-mini", api_key=SecretStr("test")),
        include_secrets=True,
    )

    def llm_profiles() -> LLMProfileStore:
        return LLMProfileStore(base_dir=profiles_dir)

    with (
        patch(
            "openhands.agent_server.openai.service.get_llm_profile_store", llm_profiles
        ),
        patch("openhands.agent_server.launch.get_llm_profile_store", llm_profiles),
    ):
        with live_server_env(tmp_path, monkeypatch) as env:
            with httpx.Client() as client:
                models_response = client.get(f"{env['host']}/v1/models", timeout=2.0)
                assert models_response.status_code == 200
                assert models_response.json()["data"] == [
                    {
                        "id": "openhands_smoke",
                        "object": "model",
                        "created": 0,
                        "owned_by": "openhands",
                    }
                ]

                response = client.post(
                    f"{env['host']}/v1/chat/completions",
                    json={
                        "model": "openhands_smoke",
                        "messages": [
                            {"role": "system", "content": "Answer briefly."},
                            {"role": "user", "content": "Say hello."},
                        ],
                    },
                    timeout=10.0,
                )
                assert response.status_code == 200
                body = response.json()
                assert body["object"] == "chat.completion"
                assert body["model"] == "openhands_smoke"
                assert body["choices"][0]["message"] == {
                    "role": "assistant",
                    "content": "Hello from patched LLM",
                }
                assert body["usage"] == {
                    "prompt_tokens": 7,
                    "completion_tokens": 5,
                    "total_tokens": 12,
                }
                conversation_id = response.headers["X-OpenHands-ServerConversation-ID"]
                UUID(conversation_id)
                persisted_response = client.get(
                    f"{env['host']}/api/conversations/{conversation_id}", timeout=2.0
                )
                assert persisted_response.status_code == 200
                assert persisted_response.json()["workspace"]["working_dir"] == str(
                    env["workspace_path"]
                )

                reused_response = client.post(
                    f"{env['host']}/v1/chat/completions",
                    headers={"X-OpenHands-ServerConversation-ID": conversation_id},
                    json={
                        "model": "openhands_smoke",
                        "messages": [
                            {"role": "user", "content": "Say hello again."},
                        ],
                    },
                    timeout=10.0,
                )
                assert reused_response.status_code == 200
                assert (
                    reused_response.headers["X-OpenHands-ServerConversation-ID"]
                    == conversation_id
                )
                assert reused_response.json()["choices"][0]["message"] == {
                    "role": "assistant",
                    "content": "Hello from patched LLM",
                }

                from openai import BadRequestError, OpenAI

                openai_client = OpenAI(
                    api_key="unused",
                    base_url=f"{env['host']}/v1",
                    timeout=10,
                )
                stream = openai_client.chat.completions.create(
                    model="openhands_smoke",
                    messages=[
                        {"role": "developer", "content": "Answer tersely."},
                        {"role": "user", "content": "Say hello as a stream."},
                    ],
                    stream=True,
                    stream_options={"include_usage": True},
                    user="compat-test-user",
                )
                chunks = list(stream)
                streamed_text = "".join(
                    chunk.choices[0].delta.content or ""
                    for chunk in chunks
                    if chunk.choices
                )
                usage_chunks = [chunk.usage for chunk in chunks if chunk.usage]
                assert streamed_text == "Hello from patched LLM"
                assert usage_chunks[-1].prompt_tokens == 7
                assert usage_chunks[-1].completion_tokens == 5
                assert usage_chunks[-1].total_tokens == 12

                stream = openai_client.chat.completions.create(
                    model="openhands_smoke",
                    messages=[
                        {
                            "role": "user",
                            "content": "Say hello as a default stream.",
                        },
                    ],
                    stream=True,
                )
                chunks = list(stream)
                streamed_text = "".join(
                    chunk.choices[0].delta.content or ""
                    for chunk in chunks
                    if chunk.choices
                )
                usage_chunks = [chunk.usage for chunk in chunks if chunk.usage]
                assert streamed_text == "Hello from patched LLM"
                assert usage_chunks == []

                raw_response = openai_client.responses.with_raw_response.create(
                    model="openhands_smoke",
                    instructions="Answer briefly.",
                    input="Say hello through Responses.",
                    store=False,
                )
                responses_result = raw_response.parse()
                assert responses_result.object == "response"
                assert responses_result.status == "completed"
                assert responses_result.model == "openhands_smoke"
                assert responses_result.output_text == "Hello from patched LLM"
                assert responses_result.previous_response_id is None
                assert responses_result.usage is not None
                assert responses_result.usage.input_tokens == 7
                assert responses_result.usage.output_tokens == 5
                assert responses_result.usage.total_tokens == 12
                assert responses_result.id.startswith("resp_")
                UUID(hex=responses_result.id.removeprefix("resp_"))
                response_system_text = "\n".join(
                    part.text
                    for message in patched_llm[-1]
                    if message.role == "system"
                    for part in message.content
                    if isinstance(part, TextContent)
                )
                response_user_text = "\n".join(
                    part.text
                    for message in patched_llm[-1]
                    if message.role == "user"
                    for part in message.content
                    if isinstance(part, TextContent)
                )
                assert "Answer briefly." in response_system_text
                assert "Answer briefly." not in response_user_text
                assert "Say hello through Responses." in response_user_text

                responses_conversation_id = raw_response.headers[
                    "X-OpenHands-ServerConversation-ID"
                ]
                UUID(responses_conversation_id)

                llm_calls_before_rejected_continuation = len(patched_llm)
                with pytest.raises(BadRequestError) as exc_info:
                    openai_client.responses.create(
                        model="openhands_smoke",
                        input="This must not continue server-side.",
                        previous_response_id=responses_result.id,
                        store=False,
                    )
                assert exc_info.value.status_code == 400
                assert exc_info.value.response.json()["detail"] == (
                    "previous_response_id is not supported; replay input items instead"
                )
                assert len(patched_llm) == llm_calls_before_rejected_continuation

                second_stateless_response = (
                    openai_client.responses.with_raw_response.create(
                        model="openhands_smoke",
                        input=[
                            {
                                "role": "developer",
                                "content": "Use replayed context.",
                            },
                            {
                                "role": "user",
                                "content": "Say hello through Responses.",
                            },
                            *[
                                cast(
                                    ResponseInputItemParam,
                                    item.model_dump(mode="json", exclude_none=True),
                                )
                                for item in responses_result.output
                            ],
                            {
                                "role": "user",
                                "content": "Follow up using the prior answer.",
                            },
                        ],
                        store=False,
                    )
                )
                second_stateless_result = second_stateless_response.parse()
                assert second_stateless_result.output_text == "Hello from patched LLM"
                assert (
                    second_stateless_response.headers[
                        "X-OpenHands-ServerConversation-ID"
                    ]
                    != responses_conversation_id
                )
                stateless_system_text = "\n".join(
                    part.text
                    for message in patched_llm[-1]
                    if message.role == "system"
                    for part in message.content
                    if isinstance(part, TextContent)
                )
                stateless_history_text = "\n".join(
                    part.text
                    for message in patched_llm[-1]
                    if message.role == "user"
                    for part in message.content
                    if isinstance(part, TextContent)
                )
                assert "Use replayed context." in stateless_system_text
                assert "Use replayed context." not in stateless_history_text
                assert '<message role="user">' in stateless_history_text
                assert '<message role="assistant">' in stateless_history_text
                assert "Say hello through Responses." in stateless_history_text
                assert "Hello from patched LLM" in stateless_history_text
                assert "Follow up using the prior answer." in stateless_history_text

                streaming_response = client.post(
                    f"{env['host']}/v1/responses",
                    json={
                        "model": "openhands_smoke",
                        "input": "This must not run as a buffered stream.",
                        "stream": True,
                    },
                    timeout=2.0,
                )
                assert streaming_response.status_code == 400
                assert streaming_response.json()["detail"] == (
                    "Streaming responses are not supported yet"
                )

                store_response = client.post(
                    f"{env['host']}/v1/responses",
                    json={
                        "model": "openhands_smoke",
                        "input": "This must not run as a stored response.",
                        "store": True,
                    },
                    timeout=2.0,
                )
                assert store_response.status_code == 400
                assert store_response.json()["detail"] == (
                    "Persistent response storage (store=True) is not supported yet"
                )


def test_openai_gateway_replays_frozen_llm_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import asyncio

    from openai import OpenAI

    from openhands.agent_server import (
        config as config_module,
        conversation_service as service_module,
    )
    from openhands.agent_server.models import StartConversationRequest
    from openhands.sdk import Message, TextContent
    from openhands.sdk.llm.llm_profile_store import LLMProfileStore
    from openhands.sdk.testing import TestLLM
    from openhands.sdk.workspace import LocalWorkspace

    monkeypatch.setattr(config_module, "_default_config", None)
    monkeypatch.setattr(service_module, "_conversation_service", None)
    monkeypatch.delenv("OH_WEBHOOKS_0_BASE_URL", raising=False)

    fixtures_dir = Path(__file__).parents[1] / "fixtures" / "openai_gateway"
    fixtures = [
        json.loads((fixtures_dir / "openai_nano_completion.json").read_text()),
        json.loads((fixtures_dir / "litellm_haiku_completion.json").read_text()),
    ]

    profiles_dir = tmp_path / "profiles"
    store = LLMProfileStore(base_dir=profiles_dir)
    for fixture in fixtures:
        store.save(
            fixture["profile_name"],
            LLM(model=fixture["backing_model"], api_key=SecretStr("unused")),
            include_secrets=True,
        )

    async def start_conversation_with_test_llm(conversation_service, llm: TestLLM):
        request = StartConversationRequest(
            agent=Agent(
                llm=LLM(model="gpt-4o-mini", api_key=SecretStr("unused")),
                tools=[],
            ),
            workspace=LocalWorkspace(working_dir=str(tmp_path / "workspace")),
            autotitle=False,
        )
        info, _ = await conversation_service.start_conversation(request)
        event_service = await conversation_service.get_event_service(info.id)
        assert event_service is not None
        event_service.get_conversation().switch_llm(llm)
        return info.id

    with patch(
        "openhands.agent_server.openai.service.get_llm_profile_store",
        lambda: LLMProfileStore(base_dir=profiles_dir),
    ):
        with live_server_env(tmp_path, monkeypatch) as env:
            for fixture in fixtures:
                expected_content = fixture["response"]["choices"][0]["message"][
                    "content"
                ]
                llm = TestLLM.from_messages(
                    [
                        Message(
                            role="assistant",
                            content=[TextContent(text=expected_content)],
                        )
                    ],
                    model=fixture["backing_model"],
                    usage_id=f"frozen-{fixture['profile_name']}",
                )
                conversation_id = asyncio.run(
                    start_conversation_with_test_llm(env["conversation_service"], llm)
                )
                client = OpenAI(
                    api_key="unused",
                    base_url=f"{env['host']}/v1",
                    default_headers={
                        "X-OpenHands-ServerConversation-ID": str(conversation_id)
                    },
                    timeout=10,
                )
                completion = client.chat.completions.create(
                    model=fixture["gateway_model"],
                    messages=fixture["messages"],
                )

                assert completion.model == fixture["gateway_model"]
                assert completion.choices[0].message.content == expected_content
                assert llm.call_count == 1


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="The live bash endpoint depends on the Unix terminal backend.",
)
def test_bash_command_endpoint_with_live_server(server_env):
    """集成测试用于通过实时服务器执行 bash 命令。

    此测试通过以下方式验证 /api/bash/start_bash_command 端点端到端正常工作：
    1. 使用 bash 端点启动真正的 FastAPI 服务器
    2. 创建一个指向该服务器的 RemoteWorkspace
    3. 执行真正的 bash 命令
    4. 验证实际命令输出

    这是针对问题 #866 的回归测试，其中 bash 执行由于使用错误的端点 URL 而被破坏。
    """
    # 创建一个指向实时服务器的 RemoteWorkspace
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/test_workspace"
    )

    # 执行可生成可验证输出的 bash 命令测试多个命令以确保命令链正常工作
    #
    command = "echo 'Hello from live bash endpoint!' && echo 'Line 2' && expr 5 + 3"
    result = workspace.execute_command(command, timeout=10.0)

    # 验证命令执行成功
    assert result.exit_code == 0, (
        f"Command failed with exit code {result.exit_code}. "
        f"stdout: {result.stdout}, stderr: {result.stderr}"
    )
    assert result.timeout_occurred is False, (
        "Command timed out - this suggests the endpoint is not working correctly"
    )

    # 验证实际输出包含我们所有预期的文本
    assert "Hello from live bash endpoint!" in result.stdout, (
        f"Expected 'Hello from live bash endpoint!' not found in stdout: "
        f"{result.stdout}"
    )
    assert "Line 2" in result.stdout, (
        f"Expected 'Line 2' not found in stdout: {result.stdout}"
    )
    assert "8" in result.stdout, (
        f"Expected '8' (result of 5+3) not found in stdout: {result.stdout}"
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="The live bash endpoint depends on the Unix terminal backend.",
)
def test_stop_bash_command_endpoint_with_live_server(server_env):
    """通过实时服务器端到端停止长时间运行的命令。"""
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/test_workspace"
    )
    command_id = workspace.start_command("sleep 30", timeout=60.0)
    workspace.stop_command(command_id)

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        output = workspace.get_command_output(command_id)
        if output is not None and output.get("exit_code") is not None:
            break
        time.sleep(0.2)
    else:
        pytest.fail(f"command {command_id} did not finish after stop")


def test_file_upload_endpoint_with_live_server(server_env, tmp_path: Path):
    """集成测试用于通过实时服务器上传文件。

    此测试通过以下方式验证 /api/file/upload 端点端到端正常工作：
    1. 启动真实的 FastAPI 服务器并上传文件端点
    2. 创建一个指向该服务器的 RemoteWorkspace
    3. 创建测试文件并上传
    4. 验证文件已上传到正确的位置且内容正确
    """
    # 创建一个指向实时服务器的 RemoteWorkspace
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/test_workspace"
    )

    # 创建测试文件上传
    test_file = tmp_path / "test_upload.txt"
    test_content = "Hello from file upload test!\nThis is line 2.\n"
    test_file.write_text(test_content)

    # 定义目标路径（对于服务器来说必须是绝对路径）
    destination = server_env["workspace_path"] / "uploaded_file.txt"
    destination_remote = destination.as_posix()

    # 上传文件
    result = workspace.file_upload(str(test_file), destination)

    # 验证上传是否成功
    assert result.success is True, (
        f"File upload failed. Error: {result.error}, "
        f"Source: {result.source_path}, Destination: {result.destination_path}"
    )
    assert result.source_path == str(test_file), (
        f"Expected source_path to be {test_file}, got {result.source_path}"
    )
    assert result.destination_path == destination_remote, (
        f"Expected destination_path to be {destination_remote}, "
        f"got {result.destination_path}"
    )

    downloaded_file = tmp_path / "downloaded_upload.txt"
    download_result = workspace.file_download(destination, downloaded_file)
    assert download_result.success is True, (
        f"File download failed. Error: {download_result.error}, "
        f"Source: {download_result.source_path}, "
        f"Destination: {download_result.destination_path}"
    )
    assert downloaded_file.read_text() == test_content


def test_conversation_stats_with_live_server(
    server_env, monkeypatch: pytest.MonkeyPatch
):
    """集成测试验证对话统计信息是否正确传播。

    此测试验证了问题 #1041 的修复，其中累积成本始终为 0。 它检查：
    1. RemoteConversation 从正确的“统计”字段（而不是“conversation_stats”）读取统计信
    息
    2. run() 完成后传播统计更新
    3. 正确跟踪累计成本和词元用量

    这是针对字段不匹配和状态更新问题的回归测试。
    """

    def fake_completion_with_cost(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.message import Message
        from openhands.sdk.llm.utils.metrics import TokenUsage

        # 使用一条辅助消息创建最小的 ModelResponse
        litellm_msg = LiteLLMMessage.model_validate(
            {"role": "assistant", "content": "Test response"}
        )
        raw_response = ModelResponse(
            id="test-resp-with-cost",
            created=int(time.time()),
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
        )

        # 转换为 OpenHands 消息
        message = Message.from_llm_chat_message(litellm_msg)

        # 模拟 LLM 指标中的成本累积 LLM 应该具有跟踪成本的指标
        #
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot

        if self.metrics:
            self.metrics.add_cost(0.0025)
            self.metrics.add_token_usage(
                prompt_tokens=100,
                completion_tokens=50,
                cache_read_tokens=0,
                cache_write_tokens=0,
                context_window=8192,
                response_id="test-resp-with-cost",
                reasoning_tokens=0,
            )
            metrics_snapshot = self.metrics.get_snapshot()
        else:
            # 如果不存在指标，则创建默认指标快照
            metrics_snapshot = MetricsSnapshot(
                model_name=self.model,
                accumulated_cost=0.0025,
                accumulated_token_usage=TokenUsage(
                    model=self.model,
                    prompt_tokens=100,
                    completion_tokens=50,
                    response_id="test-resp-with-cost",
                ),
            )

        return LLMResponse(
            message=message, metrics=metrics_snapshot, raw_response=raw_response
        )

    # 使用我们的成本跟踪版本修补 LLM.completion
    monkeypatch.setattr(LLM, "completion", fake_completion_with_cost, raising=True)

    async def fake_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        return fake_completion_with_cost(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", fake_acompletion, raising=True)

    # 使用真实的 LLM 对象创建智能体
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[])

    # 通过指向实时服务器的工厂创建对话
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(agent=agent, workspace=workspace)

    # 验证初始统计数据为空/零
    initial_stats = conv.conversation_stats
    assert initial_stats is not None
    initial_cost = initial_stats.get_combined_metrics().accumulated_cost
    assert initial_cost == 0.0, f"Expected initial cost to be 0.0, got {initial_cost}"

    # 发送消息并运行对话
    conv.send_message("Test message")
    conv.run()

    # 等待对话完成并更新统计信息该修复确保统计信息在 run() 完成后发布
    #
    max_attempts = 50
    for attempt in range(max_attempts):
        try:
            stats = conv.conversation_stats
            combined_metrics = stats.get_combined_metrics()
            accumulated_cost = combined_metrics.accumulated_cost

            # 检查我们是否获得非零成本（统计数据已更新）
            if accumulated_cost > 0:
                # 验证统计数据是否正确填充
                assert accumulated_cost > 0, (
                    f"Expected accumulated_cost > 0 after run(), got {accumulated_cost}"
                )

                # 验证词元用量已被跟踪
                if combined_metrics.accumulated_token_usage:
                    assert combined_metrics.accumulated_token_usage.prompt_tokens > 0, (
                        "Expected prompt_tokens > 0 after run()"
                    )
                    assert (
                        combined_metrics.accumulated_token_usage.completion_tokens > 0
                    ), "Expected completion_tokens > 0 after run()"

                # 成功 - 我们获得了更新的统计数据
                break
        except (KeyError, AttributeError, AssertionError) as e:
            if attempt == max_attempts - 1:
                raise AssertionError(
                    f"Stats not properly updated after {max_attempts} attempts. "
                    f"Last error: {e}"
                )
        time.sleep(0.1)

    # 最终验证：统计数据是从“stats”字段读取的，而不是“conversation_stats”
    info = conv.state._get_conversation_info()
    assert "stats" in info, "Expected 'stats' field in conversation info"

    # 验证 RemoteConversation 是否正确读取“stats”
    stats_from_field = info.get("stats", {})
    assert stats_from_field, "Expected non-empty stats in the 'stats' field after run()"

    conv.close()


def test_events_not_lost_during_client_disconnection(
    server_env, monkeypatch: pytest.MonkeyPatch
):
    """测试事件在客户端断开连接期间是否丢失不。

    这是针对 PR #1791 评论中描述的错误的回归测试，其中客户端断开连接期间发出的事件可
    能会丢失。 该修复在 run() 完成后添加了协调同步，以确保捕获所有事件
    。

    最初的错误场景：
    1. 测试与模拟的 `finish` 工具调用进行对话
    2. 服务器发出 `ActionEvent` + `ObservationEvent`
    3. 当状态变为“完成”时返回`conv.run()`
    4. 客户端开始关闭 WebSocket
    5. 断开连接期间发出的事件可能无法通过 WebSocket 传递

    修复：run() 完成后，我们调用 reconcile() 来获取可能通过 WebSocket 错过的任何事件
    。 这可确保客户端始终拥有所有事件的完整视图。

    请参阅PR #1791 反馈以获取详细信息：
    https://github.com/OpenHands/software-agent-sdk/pull/1791#pullrequestreview-3694259068
    """  # noqa: E501

    def fake_completion_with_finish_tool(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.message import Message
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot

        # 返回完成工具调用结束对话
        litellm_msg = LiteLLMMessage.model_validate(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_finish",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": '{"message": "Task complete"}',
                        },
                    }
                ],
            }
        )

        raw_response = ModelResponse(
            id="test-resp-finish",
            created=int(time.time()),
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
        )

        message = Message.from_llm_chat_message(litellm_msg)
        metrics_snapshot = MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=None,
        )

        return LLMResponse(
            message=message, metrics=metrics_snapshot, raw_response=raw_response
        )

    monkeypatch.setattr(
        LLM, "completion", fake_completion_with_finish_tool, raising=True
    )

    async def fake_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        return fake_completion_with_finish_tool(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", fake_acompletion, raising=True)

    # 创建一个带有空工具列表的智能体（finish 是内置工具）
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[])

    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(agent=agent, workspace=workspace)

    # 发送消息并运行 - 这将触发完成工具
    conv.send_message("Complete the task")
    conv.run()

    # 此时，conv.run()已经返回，因为状态变为“完成”。 WebSocket 客户端可能已开始关闭，但
    # 服务器可能仍在尝试发送事件。
    #

    # 获取通过 WebSocket 接收的事件（缓存在 RemoteEventsList 中）
    ws_events = list(conv.state.events)

    # 直接从 REST API 获取事件以获取权威列表这绕过 WebSocket 并显示服务器上实际已持久化
    # 的内容
    #
    with httpx.Client(base_url=server_env["host"]) as client:
        response = client.get(
            f"/api/conversations/{conv._id}/events/search",
            params={"limit": 100},
        )
        response.raise_for_status()
        rest_data = response.json()
        rest_events = [Event.model_validate(item) for item in rest_data["items"]]

    # 每个源中计数 ActionEvents
    ws_action_events = [
        e for e in ws_events if isinstance(e, ActionEvent) and e.tool_name == "finish"
    ]
    rest_action_events = [
        e for e in rest_events if isinstance(e, ActionEvent) and e.tool_name == "finish"
    ]

    ws_observation_events = [
        e
        for e in ws_events
        if isinstance(e, ObservationEvent) and e.tool_name == "finish"
    ]
    rest_observation_events = [
        e
        for e in rest_events
        if isinstance(e, ObservationEvent) and e.tool_name == "finish"
    ]

    # 记录我们发现的内容以进行调试
    ws_event_summary = [
        f"{type(e).__name__}({getattr(e, 'tool_name', 'N/A')})" for e in ws_events
    ]
    rest_event_summary = [
        f"{type(e).__name__}({getattr(e, 'tool_name', 'N/A')})" for e in rest_events
    ]

    conv.close()

    # 问题：在客户端断开连接时，事件可能会丢失 REST API 应该总是有事件（它们是已持久化）
    #  WebSocket 如果在断开连接时发出，可能会丢失事件
    #

    # 首先，验证 REST API 是否具有预期事件（健全性检查）
    assert len(rest_action_events) >= 1, (
        f"REST API should have ActionEvent with finish tool. "
        f"REST events: {rest_event_summary}"
    )
    assert len(rest_observation_events) >= 1, (
        f"REST API should have ObservationEvent with finish tool. "
        f"REST events: {rest_event_summary}"
    )

    # 验证客户端是否拥有所有事件（协调应该已获取任何遗漏的事件）
    ws_has_action = len(ws_action_events) >= 1
    ws_has_observation = len(ws_observation_events) >= 1

    # 这些断言验证了修复工作有效 - 调和确保没有事件丢失
    assert ws_has_action, (
        f"ActionEvent with finish tool not found in client events. "
        f"REST API has {len(rest_action_events)} ActionEvent(s) but client has "
        f"{len(ws_action_events)}. Reconciliation should have fetched missing events. "
        f"Client events: {ws_event_summary}. REST events: {rest_event_summary}"
    )

    assert ws_has_observation, (
        f"ObservationEvent with finish tool not found in client events. "
        f"Client events: {ws_event_summary}"
    )


def test_post_run_reconcile_needed_under_ws_callback_lag(
    server_env, monkeypatch: pytest.MonkeyPatch
):
    """*客户端*尾部事件竞赛的受控重现。

    我们延迟了客户端 WS 中完成工具 WS 事件的处理回调。 这可以使 `conv.run()` 在 WS 线
    程附加最终操作/观察事件之前返回（轮询看到最终状态）。

    然后我们展示运行完成后的 REST 协调可以恢复这些事件。

    此测试有意保守：它不会改变生产逻辑
    except for injecting a delay into the client-side callback.
    """

    ws_delay_s = 0.75

    def fake_completion_with_finish_tool(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.message import Message
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot

        litellm_msg = LiteLLMMessage.model_validate(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_finish",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": '{"message": "Task complete"}',
                        },
                    }
                ],
            }
        )

        raw_response = ModelResponse(
            id="test-resp-finish",
            created=int(time.time()),
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
        )

        message = Message.from_llm_chat_message(litellm_msg)
        metrics_snapshot = MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=None,
        )

        return LLMResponse(
            message=message, metrics=metrics_snapshot, raw_response=raw_response
        )

    monkeypatch.setattr(
        LLM, "completion", fake_completion_with_finish_tool, raising=True
    )

    async def fake_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        return fake_completion_with_finish_tool(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", fake_acompletion, raising=True)

    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[])
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )

    conv: RemoteConversation = Conversation(agent=agent, workspace=workspace)

    # 仅为完成操作/观察事件注入 WS 滞后 **。
    assert conv._ws_client is not None
    orig_cb = conv._ws_client.callback

    def delayed_cb(event: Event) -> None:
        if (
            isinstance(event, (ActionEvent, ObservationEvent))
            and getattr(event, "tool_name", None) == "finish"
        ):
            time.sleep(ws_delay_s)
        orig_cb(event)

    conv._ws_client.callback = delayed_cb

    conv.send_message("Complete the task")
    conv.run()

    ws_events = list(conv.state.events)

    with httpx.Client(base_url=server_env["host"]) as client:
        response = client.get(
            f"/api/conversations/{conv._id}/events/search",
            params={"limit": 100},
        )
        response.raise_for_status()
        rest_data = response.json()
        rest_events = [Event.model_validate(item) for item in rest_data["items"]]

    ws_action = [
        e for e in ws_events if isinstance(e, ActionEvent) and e.tool_name == "finish"
    ]
    rest_action = [
        e for e in rest_events if isinstance(e, ActionEvent) and e.tool_name == "finish"
    ]

    # 服务器必须有已持久化完成ActionEvent。
    assert len(rest_action) >= 1

    # 在 WS 滞后的情况下，客户端 * 可能 * 立即丢失它。 如果我们已经有了它，系统就会正常
    # 运行，而无需在此时间进行运行后协调。
    #
    # 我们必须始终确保 reconcile() 无害并产生完整的事件列表。
    #
    if len(ws_action) == 0:
        # 完成后协调应获取丢失的事件。
        conv.state.events.reconcile()
        ws_events_after = list(conv.state.events)
        ws_action_after = [
            e
            for e in ws_events_after
            if isinstance(e, ActionEvent) and e.tool_name == "finish"
        ]
        assert len(ws_action_after) >= 1
    else:
        # 仍然验证协调是否幂等/不会删除事件。
        before_ids = {e.id for e in conv.state.events}
        conv.state.events.reconcile()
        after_ids = {e.id for e in conv.state.events}
        assert before_ids.issubset(after_ids)

    conv.close()


@pytest.mark.skip(
    reason="Flaky due to WebSocket disconnect timing - ActionEvent may be emitted "
    "after client starts closing, causing delivery failure. This is a separate issue "
    "from #1785 (subscription race). Test should use REST API for event verification."
)
def test_security_risk_field_with_live_server(
    server_env, monkeypatch: pytest.MonkeyPatch
):
    """集成测试验证 security_risk 字段功能。

    此测试验证了问题 #819 的修复，其中 security_risk 字段处理不一致。 它测试：
    1. 操作成功执行并提供了 security_risk
    2. 没有 security_risk 的操作成功执行（默认为 UNKNOWN）

    这是一个回归测试，生成一个真实的 Agent Server，以确保 security_risk 字段处理的端
    到端功能。
    """

    # 跟踪我们正在使用哪个完成调用来控制行为
    call_count = {"count": 0}

    def fake_completion_with_tool_calls(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.message import Message
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot

        call_count["count"] += 1

        # 第一次调用：return 工具调用 WITHOUT security_risk（配置分析器时测试错误事件）
        #
        if call_count["count"] == 1:
            litellm_msg = LiteLLMMessage.model_validate(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "finish",
                                "arguments": '{"message": "Task complete"}',
                            },
                        }
                    ],
                }
            )
        # 第二次调用：return 工具调用 WITH security_risk（错误后测试是否成功执行）
        #
        elif call_count["count"] == 2:
            litellm_msg = LiteLLMMessage.model_validate(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "finish",
                                "arguments": (
                                    '{"message": "Task complete", '
                                    '"security_risk": "LOW"}'
                                ),
                            },
                        }
                    ],
                }
            )
        # 第三次通话：简单的消息即可完成
        else:
            litellm_msg = LiteLLMMessage.model_validate(
                {"role": "assistant", "content": "Done"}
            )

        raw_response = ModelResponse(
            id=f"test-resp-{call_count['count']}",
            created=int(time.time()),
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
        )

        message = Message.from_llm_chat_message(litellm_msg)
        metrics_snapshot = MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=None,
        )

        return LLMResponse(
            message=message, metrics=metrics_snapshot, raw_response=raw_response
        )

    monkeypatch.setattr(
        LLM, "completion", fake_completion_with_tool_calls, raising=True
    )

    async def fake_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        return fake_completion_with_tool_calls(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", fake_acompletion, raising=True)

    # 创建智能体（安全分析器功能已已弃用并删除）使用空工具列表，因为工具需要在服务器中注
    # 册
    #
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(
        llm=llm,
        tools=[],
    )

    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(agent=agent, workspace=workspace)

    # 第 1 步：发送消息 WITHOUT security_risk - 仍应执行（默认为 UNKNOWN）
    #
    conv.send_message("Complete the task")
    conv.run()

    # 等待操作事件 - 即使没有 security_risk 也应该成功
    found_action_without_risk = False
    for attempt in range(50):  # 长达〜5秒
        events = conv.state.events
        for e in events:
            if isinstance(e, ActionEvent) and e.tool_name == "finish":
                # 验证其是否具有安全风险属性
                assert hasattr(e, "security_risk"), (
                    "Expected ActionEvent to have security_risk attribute"
                )
                found_action_without_risk = True
                break
        if found_action_without_risk:
            break
        time.sleep(0.1)

    assert found_action_without_risk, (
        "Expected to find ActionEvent with finish tool even without security_risk"
    )

    conv.close()

    # 测试验证：
    # 1. 无需 security_risk 即可执行操作（默认为 UNKNOWN）
    # 2. ActionEvent 始终具有 security_risk 属性


def test_hook_config_sent_to_server(
    server_env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """测试 hook_config 是否正确发送到服务器并执行挂钩。

    这验证了修复了 hook_config 被 RemoteConversation 接受但未发送到服务器的问题，这意
    味着服务器端钩子 (PreToolUse,
    PostToolUse, UserPromptSubmit, Stop) 从未执行。

    测试：
    1. 配置 post_tool_use 和停止钩子
    2. 使用修补的 LLM 返回完成工具调用
    3. 验证两种钩子类型都收到 HookExecutionEvent 事件
    """
    # 创建输出 JSON 的钩子脚本以指示执行成功
    post_tool_hook = tmp_path / "post_tool_hook.sh"
    post_tool_hook.write_text('#!/bin/bash\necho \'{"decision": "allow"}\'\nexit 0\n')
    post_tool_hook.chmod(0o755)

    stop_hook = tmp_path / "stop_hook.sh"
    stop_hook.write_text('#!/bin/bash\necho \'{"decision": "allow"}\'\nexit 0\n')
    stop_hook.chmod(0o755)

    hook_config = HookConfig(
        post_tool_use=[
            HookMatcher(
                matcher="*",
                hooks=[
                    HookDefinition(
                        command=str(post_tool_hook),
                        timeout=5,
                    )
                ],
            )
        ],
        stop=[
            HookMatcher(
                matcher="*",
                hooks=[
                    HookDefinition(
                        command=str(stop_hook),
                        timeout=5,
                    )
                ],
            )
        ],
    )

    # 创建一个修补的 LLM，它返回完成工具调用以触发钩子
    call_count = {"count": 0}

    def fake_completion_with_finish(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.message import Message
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot

        is_title_call = not tools
        if not is_title_call:
            call_count["count"] += 1

        if is_title_call:
            litellm_msg = LiteLLMMessage.model_validate(
                {"role": "assistant", "content": "Generated title"}
            )
        # 第一个智能体调用触发 PostToolUse 和 Stop 挂钩。
        elif call_count["count"] == 1:
            litellm_msg = LiteLLMMessage.model_validate(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "finish",
                                "arguments": '{"message": "Task complete"}',
                            },
                        }
                    ],
                }
            )
        else:
            # 后续调用：简单消息
            litellm_msg = LiteLLMMessage.model_validate(
                {"role": "assistant", "content": "Done"}
            )

        raw_response = ModelResponse(
            id=f"test-resp-{call_count['count']}",
            created=int(time.time()),
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
        )

        message = Message.from_llm_chat_message(litellm_msg)
        metrics_snapshot = MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=None,
        )

        return LLMResponse(
            message=message, metrics=metrics_snapshot, raw_response=raw_response
        )

    monkeypatch.setattr(LLM, "completion", fake_completion_with_finish, raising=True)

    async def fake_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        return fake_completion_with_finish(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", fake_acompletion, raising=True)

    # 创建智能体
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[])

    # 通过工厂与 hook_config 创建对话
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(
        agent=agent,
        workspace=workspace,
        hook_config=hook_config,
    )

    # 验证对话已成功创建
    assert conv._id is not None

    # 发送消息并运行 - 这会触发完成工具调用
    conv.send_message("Complete the task")
    conv.run()

    # 等待接收事件并检查 HookExecutionEvents
    found_post_tool_use_hook = False
    found_stop_hook = False
    events: list[Event] = []

    for attempt in range(50):  # 长达〜5秒
        events = list(conv.state.events)
        for e in events:
            if isinstance(e, HookExecutionEvent):
                if e.hook_event_type == "PostToolUse":
                    found_post_tool_use_hook = True
                    # 验证钩子执行成功
                    assert e.success is True
                    assert e.blocked is False
                    assert e.exit_code == 0
                    assert str(post_tool_hook) in e.hook_command
                elif e.hook_event_type == "Stop":
                    found_stop_hook = True
                    # 验证钩子执行成功
                    assert e.success is True
                    assert e.blocked is False
                    assert e.exit_code == 0
                    assert str(stop_hook) in e.hook_command

        if found_post_tool_use_hook and found_stop_hook:
            break
        time.sleep(0.1)

    # 断言两个钩子都被执行并且它们的事件被接收
    assert found_post_tool_use_hook, (
        "Expected HookExecutionEvent for PostToolUse hook. "
        f"Events received: {[type(e).__name__ for e in events]}"
    )
    assert found_stop_hook, (
        "Expected HookExecutionEvent for Stop hook. "
        f"Events received: {[type(e).__name__ for e in events]}"
    )

    # 验证状态转换发生（证明对话成功运行）
    state = conv.state
    assert state.execution_status.value in {"finished", "idle", "running"}

    conv.close()


def test_subagent_definitions_forwarded_to_server(server_env, patched_llm):
    """在客户端上注册的智能体定义在 HTTP 往返过程中仍然存在。

    这是针对错误的回归测试，其中服务器的委托注册表为空，因为 register_builtins_agents
    () 仅在客户端上运行。

    验证完整流程：
      客户端 register_agent(描述=AgentDefinition(...))
            （或 register_agent_if_absent(...)）
        → get_registered_agent_definitions() → POST /api/conversations 中的 JSON 载荷
         → 服务
        器 start_conversation() 反序列化并重新注册

    由于本次测试中客户端和服务器共享一个进程，因此我们在*构建载荷之后重置全局注册表*
    ，然后将POST直接发送到服务器。 服务器从 HTTP 载荷重新填充注册表（不是
    from any shared in-process state).
    """
    _reset_registry_for_tests()

    # 注册两个智能体，并提供明确定义（文件/插件风格）
    bash_def = AgentDefinition(
        name="test_bash",
        description="Command execution specialist",
        tools=["terminal"],
        system_prompt="You are a bash specialist.",
    )
    register_agent_if_absent(
        name="test_bash",
        factory_func=lambda llm: None,  # type: ignore[return-value]
        description=bash_def,
    )

    reviewer_def = AgentDefinition(
        name="test_reviewer",
        description="Code review specialist",
        tools=["terminal"],
        system_prompt="You review code for correctness.",
    )
    register_agent(
        name="test_reviewer",
        factory_func=lambda llm: None,  # type: ignore[return-value]
        description=reviewer_def,
    )

    # 发送前验证定义是否完整
    defs = get_registered_agent_definitions()
    reviewer = next(d for d in defs if d.name == "test_reviewer")
    assert reviewer.tools == ["terminal"]
    assert reviewer.system_prompt == "You review code for correctness."

    # 捕获已序列化定义，然后重置以证明服务器从 HTTP 载荷重新注册（而不是从共享进程内状态
    # ）。
    #
    all_defs = [d.model_dump(mode="json") for d in defs]
    _reset_registry_for_tests()

    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[])

    # POST 直接连接到具有已序列化定义的服务器
    payload = {
        "agent": agent.model_dump(mode="json", context={"expose_secrets": True}),
        "workspace": {"working_dir": "/tmp/workspace/project"},
        "agent_definitions": all_defs,
    }
    with httpx.Client(base_url=server_env["host"]) as client:
        resp = client.post("/api/conversations", json=payload, timeout=10.0)
        resp.raise_for_status()

    # 服务器应该重新注册 HTTP 载荷中的智能体
    info = get_factory_info()
    assert "test_bash" in info
    assert "Command execution specialist" in info
    assert "test_reviewer" in info
    assert "Code review specialist" in info

    _reset_registry_for_tests()


def test_agent_final_response_endpoint(server_env, monkeypatch: pytest.MonkeyPatch):
    """GET /api/conversations/{id}/agent_final_response 返回完成消息。

    创建一个对话，运行带有修补的 LLM 的智能体，调用
    ``finish(message="Task complete")``，然后点击端点并验证响应文本。 还检查 404 案例
    中是否存在未知对话。
    """

    call_count = {"count": 0}

    def fake_completion_with_finish(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.message import Message
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot

        is_title_call = not tools
        if not is_title_call:
            call_count["count"] += 1

        if is_title_call:
            litellm_msg = LiteLLMMessage.model_validate(
                {"role": "assistant", "content": "Generated title"}
            )
        elif call_count["count"] == 1:
            litellm_msg = LiteLLMMessage.model_validate(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "finish",
                                "arguments": ('{"message": "Task complete"}'),
                            },
                        }
                    ],
                }
            )
        else:
            litellm_msg = LiteLLMMessage.model_validate(
                {"role": "assistant", "content": "Done"}
            )

        raw_response = ModelResponse(
            id=f"test-resp-{call_count['count']}",
            created=int(time.time()),
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
        )

        message = Message.from_llm_chat_message(litellm_msg)
        metrics_snapshot = MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=None,
        )

        return LLMResponse(
            message=message,
            metrics=metrics_snapshot,
            raw_response=raw_response,
        )

    monkeypatch.setattr(LLM, "completion", fake_completion_with_finish, raising=True)

    async def fake_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        return fake_completion_with_finish(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", fake_acompletion, raising=True)

    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[])
    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(agent=agent, workspace=workspace)
    conversation_id = conv.id

    conv.send_message("Complete the task")
    conv.run()

    # 等待完成操作事件为已持久化
    for _ in range(50):
        events = list(conv.state.events)
        if any(isinstance(e, ActionEvent) and e.tool_name == "finish" for e in events):
            break
        time.sleep(0.1)

    # 点击端点并验证智能体的最终响应
    with httpx.Client(base_url=server_env["host"]) as client:
        resp = client.get(
            f"/api/conversations/{conversation_id}/agent_final_response",
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Task complete"

        # 404 表示未知对话
        from uuid import uuid4

        resp_404 = client.get(
            f"/api/conversations/{uuid4()}/agent_final_response",
            timeout=10.0,
        )
        assert resp_404.status_code == 404

    conv.close()


def test_server_info_exposes_usable_tools(server_env):
    with httpx.Client(base_url=server_env["host"]) as client:
        response = client.get("/server_info", timeout=10.0)

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("usable_tools"), list)
    assert "terminal" in payload["usable_tools"]


def test_remote_state_exposes_invoked_skills(
    server_env,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """远程智能体服务器上 `invoke_skill` 工具的端到端覆盖。

    修补 LLM 以在第一轮发出 `invoke_skill(name=...)` 工具调用，在第二轮发出停止消息，
    然后断言：

    1. 服务器记录调用并 `RemoteState.invoked_skills` 通过 REST 响应模型显示它。
    2. 工具的ObservationEvent 包含了真实技能目录的地理位置页脚，证明了页脚逻辑通过远
    程执行路径（技能源在服务器端解析）有效。
    """
    call_count = {"count": 0}

    # 真实的磁盘上 SKILL.md，因此页脚解析为真实的目录。
    skill_dir = tmp_path / "frobnitz-converter"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("placeholder")

    def fake_completion(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.message import Message
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot

        is_title_call = not tools
        if not is_title_call:
            call_count["count"] += 1

        if is_title_call:
            litellm_msg = LiteLLMMessage.model_validate(
                {"role": "assistant", "content": "Generated title"}
            )
        elif call_count["count"] == 1:
            litellm_msg = LiteLLMMessage.model_validate(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_invoke",
                            "type": "function",
                            "function": {
                                "name": "invoke_skill",
                                "arguments": '{"name": "frobnitz-converter"}',
                            },
                        }
                    ],
                }
            )
        else:
            litellm_msg = LiteLLMMessage.model_validate(
                {"role": "assistant", "content": "Done"}
            )

        raw_response = ModelResponse(
            id=f"test-resp-{call_count['count']}",
            created=int(time.time()),
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
        )
        message = Message.from_llm_chat_message(litellm_msg)
        metrics_snapshot = MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=None,
        )
        return LLMResponse(
            message=message, metrics=metrics_snapshot, raw_response=raw_response
        )

    monkeypatch.setattr(LLM, "completion", fake_completion, raising=True)

    async def fake_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        return fake_completion(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", fake_acompletion, raising=True)

    skill = Skill(
        name="frobnitz-converter",
        content="Convert frobs to meters.",
        description="Fake skill for remote-server test.",
        source=str(skill_md),
        is_agentskills_format=True,
    )
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test"))
    agent = Agent(llm=llm, tools=[], agent_context=AgentContext(skills=[skill]))

    workspace = RemoteWorkspace(
        host=server_env["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(agent=agent, workspace=workspace)

    assert conv.state.invoked_skills == []

    conv.send_message("Please run the frobnitz-converter skill.")
    conv.run()

    # 破坏 WS 填充的缓存，因此断言执行 REST
    # `ConversationInfo` 端到端响应模型。
    conv.state.refresh_from_server()
    assert conv.state.invoked_skills == ["frobnitz-converter"]
    assert call_count["count"] >= 2, (
        "Expected the agent to make a follow-up LLM call after the tool "
        "observation, proving the invoke_skill tool actually executed."
    )

    # 找到 invoke_skill ObservationEvent 并确认页脚指向技能的真实磁盘目录。
    #
    skill_observations = [
        e
        for e in conv.state.events
        if isinstance(e, ObservationEvent) and e.tool_name == "invoke_skill"
    ]
    assert skill_observations, "No ObservationEvent emitted for invoke_skill"
    obs_text = skill_observations[-1].observation.text
    skill_dir_display = skill_dir.resolve().as_posix()
    assert skill_dir_display in obs_text, (
        f"Footer missing skill directory {skill_dir_display}: {obs_text!r}"
    )
    assert obs_text.rstrip().endswith("relative to that directory.")

    conv.close()


def test_workspace_default_llm_resolves_active_profile_despite_settings_drift(
    tmp_path, monkeypatch
):
    """取消固定的自动化获取 UI 公布的活动命名配置文件。

    通过实际 HTTP 端点重现生产波动：激活 GLM，然后只对 agent_settings.llm 进行补丁，
    而保留 GPT 的活跃指针。
    RemoteWorkspace.get_llm() 必须解析 GLM 及其命名配置文件凭据。 显式配置文件选择仍
    然是替代。
    """
    with live_server_env(tmp_path, monkeypatch) as env:
        with httpx.Client(base_url=env["host"], timeout=10.0) as client:
            save_glm = client.post(
                "/api/profiles/glm-default",
                json={
                    "llm": {
                        "model": "openhands/glm-5.2",
                        "api_key": "sk-glm-key",
                    },
                    "include_secrets": True,
                },
            )
            assert save_glm.status_code == 201
            assert client.post("/api/profiles/glm-default/activate").status_code == 200

            save_explicit = client.post(
                "/api/profiles/explicit-model",
                json={
                    "llm": {
                        "model": "openrouter/explicit-model",
                        "api_key": "sk-explicit-key",
                    },
                    "include_secrets": True,
                },
            )
            assert save_explicit.status_code == 201

            drift = client.patch(
                "/api/settings",
                json={
                    "agent_settings_diff": {
                        "llm": {"model": "gpt-5.5", "api_key": None}
                    }
                },
            )
            assert drift.status_code == 200

            profiles = client.get("/api/profiles").json()
            settings = client.get("/api/settings").json()
            assert profiles["active_profile"] == "glm-default"
            assert settings["active_profile"] == "glm-default"
            assert settings["agent_settings"]["llm"]["model"] == "gpt-5.5"

        workspace = RemoteWorkspace(
            host=env["host"],
            working_dir=str(env["workspace_path"]),
        )
        default_llm = workspace.get_llm()
        assert default_llm.model == "openhands/glm-5.2"
        assert default_llm.api_key is not None
        _assert_secret(default_llm.api_key, "sk-glm-key")
        assert default_llm.usage_id == "profile:glm-default"

        # 镜像显式 AUTOMATION_MODEL/profile_name 覆盖。
        explicit_llm = workspace.get_llm(profile_name="explicit-model")
        assert explicit_llm.model == "openrouter/explicit-model"
        assert explicit_llm.api_key is not None
        _assert_secret(explicit_llm.api_key, "sk-explicit-key")
        assert explicit_llm.usage_id == "profile:explicit-model"


def test_workspace_named_llm_resolves_current_provider_credentials(
    tmp_path, monkeypatch
):
    """选择链接的配置文件可解决凭据而无需激活它。"""
    with live_server_env(tmp_path, monkeypatch) as env:
        workspace = RemoteWorkspace(
            host=env["host"], working_dir=str(env["workspace_path"])
        )
        with httpx.Client(base_url=env["host"], timeout=10.0) as client:
            settings_before = client.get("/api/settings").json()
            connection = client.post(
                "/api/llm/provider-connections",
                json={
                    "display_name": "Automation provider",
                    "provider": "openai",
                    "api_key": "sk-provider-old",
                    "base_url": "https://provider.example/v1",
                },
            )
            assert connection.status_code == 201
            connection_id = connection.json()["id"]
            saved = client.post(
                "/api/profiles/automation-model",
                json={
                    "llm": {
                        "model": "openai/gpt-4o-mini",
                        "provider_connection_id": connection_id,
                    }
                },
            )
            assert saved.status_code == 201

            detail = client.get("/api/profiles/automation-model").json()
            assert detail["config"]["api_key"] is None
            assert detail["config"]["base_url"] is None
            assert detail["api_key_set"] is True

            selected = workspace.get_llm(profile_name="automation-model")
            assert selected.model == "openai/gpt-4o-mini"
            assert selected.base_url == "https://provider.example/v1"
            assert selected.api_key is not None
            _assert_secret(selected.api_key, "sk-provider-old")

            rotated = client.patch(
                f"/api/llm/provider-connections/{connection_id}",
                json={"api_key": "sk-provider-new"},
            )
            assert rotated.status_code == 200
            selected = workspace.get_llm(profile_name="automation-model")
            assert selected.api_key is not None
            _assert_secret(selected.api_key, "sk-provider-new")

            settings_after = client.get("/api/settings").json()
            assert settings_after["active_profile"] == settings_before["active_profile"]
            assert (
                settings_after["agent_settings"]["llm"]
                == settings_before["agent_settings"]["llm"]
            )


def test_settings_and_secrets_api_with_live_server(server_env):
    """设置和机密 API 端点的端到端测试。

    通过实时智能体服务器验证完整的 REST API 设置和机密管理，包括：
    - GET/PATCH 设置
    - POST/PATCH/DELETE MCP 个服务器
    - GET/PUT/DELETE 机密
    - 机密姓名验证
    - 加密/解密往返
    """
    with httpx.Client(base_url=server_env["host"], timeout=10.0) as client:
        # ── 测试设定端点 ──────────────────────────────────────── GET设定（初始状态）
        #
        get_resp = client.get("/api/settings")
        assert get_resp.status_code == 200
        initial = get_resp.json()
        assert "agent_settings" in initial
        assert "conversation_settings" in initial
        assert "llm_api_key_is_set" in initial

        # PATCH 设置（更新 LLM 型号）
        patch_resp = client.patch(
            "/api/settings",
            json={"agent_settings_diff": {"llm": {"model": "gpt-4o"}}},
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()
        assert patched["agent_settings"]["llm"]["model"] == "gpt-4o"

        create_mcp_resp = client.post(
            "/api/settings/mcp/docs",
            json={"transport": "http", "url": "https://docs.example/mcp"},
        )
        assert create_mcp_resp.status_code == 201

        patch_mcp_resp = client.patch(
            "/api/settings/mcp/docs",
            json={"description": "Documentation"},
        )
        assert patch_mcp_resp.status_code == 200
        assert (
            patch_mcp_resp.json()["agent_settings"]["mcp_config"]["docs"]["description"]
            == "Documentation"
        )

        delete_mcp_resp = client.delete("/api/settings/mcp/docs")
        assert delete_mcp_resp.status_code == 200
        assert "docs" not in delete_mcp_resp.json()["agent_settings"]["mcp_config"]

        # ── 测试机密 CRUD 端点 ──────────────────────────────────── 列表机密（最初应为
        # 空）
        #
        list_resp = client.get("/api/settings/secrets")
        assert list_resp.status_code == 200
        assert list_resp.json()["secrets"] == []

        # 创建一个机密
        create_resp = client.put(
            "/api/settings/secrets",
            json={
                "name": "TEST_API_KEY",
                "value": "sk-test-live-server-12345",
                "description": "Test API key for live server test",
            },
        )
        assert create_resp.status_code == 200
        created = create_resp.json()
        assert created["name"] == "TEST_API_KEY"
        assert created["description"] == "Test API key for live server test"

        # 再次列出机密（应该有一个）
        list_resp = client.get("/api/settings/secrets")
        assert list_resp.status_code == 200
        secrets = list_resp.json()["secrets"]
        assert len(secrets) == 1
        assert secrets[0]["name"] == "TEST_API_KEY"
        # 值应在列表中返回不
        assert "value" not in secrets[0]

        # 获取机密值
        value_resp = client.get("/api/settings/secrets/TEST_API_KEY")
        assert value_resp.status_code == 200
        assert value_resp.text == "sk-test-live-server-12345"

        # 更新机密（更新插入）
        update_resp = client.put(
            "/api/settings/secrets",
            json={
                "name": "TEST_API_KEY",
                "value": "sk-updated-value",
                "description": "Updated description",
            },
        )
        assert update_resp.status_code == 200

        # 验证更新值
        value_resp = client.get("/api/settings/secrets/TEST_API_KEY")
        assert value_resp.status_code == 200
        assert value_resp.text == "sk-updated-value"

        invalid_update_resp = client.put(
            "/api/settings/secrets",
            json={
                "name": "TEST_API_KEY",
                "value": REDACTED_SECRET_VALUE,
                "description": "Must not persist",
            },
        )
        assert invalid_update_resp.status_code == 422
        value_resp = client.get("/api/settings/secrets/TEST_API_KEY")
        assert value_resp.status_code == 200
        assert value_resp.text == "sk-updated-value"

        invalid_create_resp = client.put(
            "/api/settings/secrets",
            json={"name": "EMPTY_SECRET", "value": ""},
        )
        assert invalid_create_resp.status_code == 422
        listed_names = {
            item["name"]
            for item in client.get("/api/settings/secrets").json()["secrets"]
        }
        assert "EMPTY_SECRET" not in listed_names

        # 创建另一个机密
        client.put(
            "/api/settings/secrets",
            json={"name": "ANOTHER_SECRET", "value": "another-value"},
        )
        list_resp = client.get("/api/settings/secrets")
        assert len(list_resp.json()["secrets"]) == 2

        # 删除一项机密
        delete_resp = client.delete("/api/settings/secrets/TEST_API_KEY")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True

        # 验证已删除
        get_deleted_resp = client.get("/api/settings/secrets/TEST_API_KEY")
        assert get_deleted_resp.status_code == 404

        # ── 测试机密名称验证 ────────────────────────────────── 名称无效：以数字开头
        #
        invalid_resp = client.put(
            "/api/settings/secrets",
            json={"name": "123_invalid", "value": "test"},
        )
        assert invalid_resp.status_code == 422

        # 名称无效：包含特殊字符
        invalid_resp = client.put(
            "/api/settings/secrets",
            json={"name": "invalid-name", "value": "test"},
        )
        assert invalid_resp.status_code == 422

        # ── 测试加密设定机密 ──────────────────────────── 更新LLMAPI密钥
        #
        patch_resp = client.patch(
            "/api/settings",
            json={"agent_settings_diff": {"llm": {"api_key": "sk-live-test-key"}}},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["llm_api_key_is_set"] is True
        # 响应应编辑密钥（无 X-Expose-机密标头）
        assert patch_resp.json()["agent_settings"]["llm"]["api_key"] == "**********"

        # 清理
        client.delete("/api/settings/secrets/ANOTHER_SECRET")


def test_interrupt_endpoint_cancels_running_conversation(
    server_env, monkeypatch: pytest.MonkeyPatch
):
    """POST /{conversation_id}/interrupt 取消正在运行的 arun() 任务。

    使用慢速 LLM（在完成期间阻止睡眠），以便对话保持在 RUNNING 足够长的时间，以便中断
    请求到达。 使用 InterruptEvent 验证对话是否转换到
    PAUSED。
    """
    import asyncio

    slow_delay = 10  # 秒 — 足够长以保证中断着陆

    def slow_completion(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        # 以 arun() 可以取消等待的协程的方式进行阻止。
        time.sleep(slow_delay)
        # 如果中断及时到达，则永远不会到达这里。
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.message import Message
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot

        litellm_msg = LiteLLMMessage.model_validate(
            {"role": "assistant", "content": "Hello"}
        )
        return LLMResponse(
            message=Message.from_llm_chat_message(litellm_msg),
            metrics=MetricsSnapshot(
                model_name="test-model",
                accumulated_cost=0.0,
                max_budget_per_task=None,
                accumulated_token_usage=None,
            ),
            raw_response=ModelResponse(
                id="test-resp",
                created=int(time.time()),
                model="test-model",
                choices=[Choices(index=0, finish_reason="stop", message=litellm_msg)],
            ),
        )

    monkeypatch.setattr(LLM, "completion", slow_completion, raising=True)

    async def slow_acompletion(self, messages, tools=None, **kwargs):  # type: ignore[no-untyped-def]
        # 使用 asyncio.sleep，以便 CancelledError 立即中断。
        await asyncio.sleep(slow_delay)
        return slow_completion(self, messages, tools, **kwargs)

    monkeypatch.setattr(LLM, "acompletion", slow_acompletion, raising=True)

    host = server_env["host"]

    with httpx.Client(base_url=host, timeout=15.0) as client:
        # 1. 创建对话
        create_resp = client.post(
            "/api/conversations",
            json={
                "agent": {
                    "llm": {"model": "gpt-4o-mini", "api_key": "test"},
                    "tools": [],
                },
                "workspace": {"working_dir": "/tmp/workspace/project"},
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        conv_id = create_resp.json()["id"]

        # 2. 发送消息（不自动运行）
        msg_resp = client.post(
            f"/api/conversations/{conv_id}/events",
            json={
                "content": [{"type": "text", "text": "Do something"}],
                "run": False,
            },
        )
        assert msg_resp.status_code == 200, msg_resp.text

        # 3. 开始运行 — 这将触发 arun() 和慢速 LLM
        run_resp = client.post(f"/api/conversations/{conv_id}/run")
        assert run_resp.status_code == 200, run_resp.text

        # 4. 短暂等待运行实际开始
        status_resp = client.get(f"/api/conversations/{conv_id}")
        for _ in range(20):
            status_resp = client.get(f"/api/conversations/{conv_id}")
            if status_resp.json().get("execution_status") == "running":
                break
            time.sleep(0.1)
        assert status_resp.json()["execution_status"] == "running", (
            f"Conversation did not reach RUNNING: {status_resp.json()}"
        )

        # 5. 打断！
        interrupt_resp = client.post(f"/api/conversations/{conv_id}/interrupt")
        assert interrupt_resp.status_code == 200, interrupt_resp.text

        # 6. 验证对话是否转换为 PAUSED
        for _ in range(50):
            status_resp = client.get(f"/api/conversations/{conv_id}")
            if status_resp.json().get("execution_status") == "paused":
                break
            time.sleep(0.1)
        assert status_resp.json()["execution_status"] == "paused", (
            f"Expected PAUSED after interrupt, got: {status_resp.json()}"
        )

        # 7. 验证 InterruptEvent 已发出
        events_resp = client.get(
            f"/api/conversations/{conv_id}/events/search",
            params={
                "kind": ("openhands.sdk.event.user_action.InterruptEvent"),
            },
        )
        assert events_resp.status_code == 200
        items = events_resp.json()["items"]
        assert len(items) >= 1, f"Expected at least one InterruptEvent, got: {items}"


@pytest.mark.parametrize(
    ("lock_file", "method", "path", "payload", "expected_status"),
    [
        ("profiles/.profiles.lock", "GET", "/v1/models", None, 200),
        (
            "profiles/.profiles.lock",
            "PATCH",
            "/api/settings",
            {"active_profile": "qa-missing"},
            404,
        ),
        (
            "agent-profiles/.agent-profiles.lock",
            "GET",
            "/api/settings/secrets?agent_profile_id=qa-missing",
            None,
            404,
        ),
    ],
)
def test_profile_store_consumers_keep_live_server_responsive(
    server_env, tmp_path, lock_file, method, path, payload, expected_status
):
    lock_path = tmp_path / ".openhands" / lock_file
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    held = FileLock(lock_path, thread_local=False)
    held.acquire()
    safety = threading.Timer(5.0, held.release)
    safety.start()
    try:
        with (
            httpx.Client(base_url=server_env["host"], timeout=10) as client,
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            waiting = executor.submit(client.request, method, path, json=payload)
            time.sleep(0.3)
            started = time.monotonic()
            alive = client.get("/alive")
            assert alive.status_code == 200
            assert time.monotonic() - started < 2.0
            assert not waiting.done()
            held.release()
            response = waiting.result(timeout=5)
            assert response.status_code == expected_status, response.text
    finally:
        safety.cancel()
        held.release(force=True)
