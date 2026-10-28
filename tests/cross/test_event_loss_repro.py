"""事件丢失的再现测试竞态条件。

此测试演示了如果没有适当的同步，当 WebSocket 回调延迟且 run() 返回之前，事件可能会丢
失。

这是针对 PR #1829 中观察到的问题的回归测试：
https://github.com/OpenHands/software-agent-sdk/actions/runs/21364607784/job/61492749827?pr=1829#step:7:5709

运行时：uv run pytest tests/cross/test_event_loss_repro.py -v
"""  # noqa: E501

import json
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse
from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.conversation import RemoteConversation
from openhands.sdk.event import ActionEvent, Event, ObservationEvent
from openhands.sdk.workspace import RemoteWorkspace
from openhands.workspace.docker.workspace import find_available_tcp_port


@pytest.fixture
def server_env_for_repro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """启动真实的 FastAPI 服务器进行再现测试。"""
    import shutil

    cwd_conversations = Path("workspace/conversations")
    if cwd_conversations.exists():
        shutil.rmtree(cwd_conversations)

    conversations_path = tmp_path / "conversations"
    workspace_path = tmp_path / "workspace"
    conversations_path.mkdir(parents=True, exist_ok=True)
    workspace_path.mkdir(parents=True, exist_ok=True)

    cfg = {
        "session_api_keys": [],
        "conversations_path": str(conversations_path),
        "workspace_path": str(workspace_path),
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg))

    monkeypatch.setenv("OPENHANDS_AGENT_SERVER_CONFIG_PATH", str(cfg_file))
    monkeypatch.delenv("OH_CONVERSATIONS_PATH", raising=False)
    monkeypatch.delenv("SESSION_API_KEY", raising=False)
    monkeypatch.delenv("OH_SESSION_API_KEYS_0", raising=False)
    monkeypatch.delenv("TMUX_TMPDIR", raising=False)

    from openhands.agent_server.api import create_app
    from openhands.agent_server.config import Config

    cfg_obj = Config.model_validate_json(cfg_file.read_text())
    app = create_app(cfg_obj)

    port = find_available_tcp_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with httpx.Client() as client:
                response = client.get(f"{base_url}/health", timeout=2.0)
                if response.status_code == 200:
                    break
        except (httpx.RequestError, httpx.TimeoutException):
            pass
        time.sleep(0.1)

    try:
        yield {"host": base_url}
    finally:
        server.should_exit = True
        thread.join(timeout=2)
        if cwd_conversations.exists():
            shutil.rmtree(cwd_conversations)


def test_event_loss_race_condition_with_ws_delay(
    server_env_for_repro, monkeypatch: pytest.MonkeyPatch
):
    """可靠地重现事件丢失竞态条件。

    此测试在 WebSocket 回调中注入延迟以模拟竞态条件，其中 run() 在事件传递之前返回。
    这再现了 PR #1829 中观察到的 CI 失败。

    竞态条件发生在以下情况：
    1. 服务器发出事件 (ActionEvent, ObservationEvent)
    2. 客户端轮询并看到“完成”状态
    3. run() 在 WebSocket 传递这些事件之前返回

    如果没有正确的处理，客户端将错过 REST API 所具有的饰面 ActionEvent 和
    ObservationEvent。
    """

    def fake_completion_with_finish_tool(
        self,
        messages,
        tools,
        add_security_risk_prediction=False,
        **kwargs,
    ):
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
        host=server_env_for_repro["host"], working_dir="/tmp/workspace/project"
    )
    conv: RemoteConversation = Conversation(agent=agent, workspace=workspace)

    # KEY：在 WebSocket 回调中为完成事件注入延迟
    # 这模拟了竞态条件，其中 run() 在事件传递之前返回。 如果没有同步机制，3 秒的延迟确保
    # 事件肯定会丢失。
    #
    ws_delay_s = 3.0
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

    # run() 返回后获取事件 IMMEDIATELY
    ws_events = list(conv.state.events)

    # 从RESTAPI中获取事件以查看服务器有什么
    with httpx.Client(base_url=server_env_for_repro["host"]) as client:
        response = client.get(
            f"/api/conversations/{conv._id}/events/search",
            params={"limit": 100},
        )
        response.raise_for_status()
        rest_data = response.json()
        rest_events = [Event.model_validate(item) for item in rest_data["items"]]

    ws_action_events = [
        e for e in ws_events if isinstance(e, ActionEvent) and e.tool_name == "finish"
    ]
    rest_action_events = [
        e for e in rest_events if isinstance(e, ActionEvent) and e.tool_name == "finish"
    ]

    ws_event_summary = [
        f"{type(e).__name__}({getattr(e, 'tool_name', 'N/A')})" for e in ws_events
    ]
    rest_event_summary = [
        f"{type(e).__name__}({getattr(e, 'tool_name', 'N/A')})" for e in rest_events
    ]

    conv.close()

    # 验证 REST API 具有预期事件（健全性检查）
    assert len(rest_action_events) >= 1, (
        f"REST API should have ActionEvent. REST events: {rest_event_summary}"
    )

    # 该断言验证了修复工作有效 - 客户端应该在 WebSocket 延迟的情况下仍然收到所有事件，因
    # 为修复确保在 run() 返回之前事件被获取。
    #
    ws_has_action = len(ws_action_events) >= 1
    assert ws_has_action, (
        f"ActionEvent with finish tool not found in client events. "
        f"REST API has {len(rest_action_events)} ActionEvent(s) but client has "
        f"{len(ws_action_events)}. This demonstrates the race condition! "
        f"Client events: {ws_event_summary}. REST events: {rest_event_summary}"
    )
