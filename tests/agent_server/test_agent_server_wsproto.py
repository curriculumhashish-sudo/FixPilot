"""集成测试验证 Agent Server 与 wsproto 一起工作。"""

import asyncio
import json
import multiprocessing
import os
import socket
import sys
import time
from uuid import uuid4

import pytest
import requests
import websockets
import websockets.exceptions


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        return s.getsockname()[1]


def _drop_site_packages_subdir_paths():
    """删除指向站点包目录 * 内部 * 的 sys.path 条目。

    此测试从 pytest-xdist 工作线程中使用 ``spawn`` start 方法生成服务器，因此子进程继
    承了工作线程的 ``sys.path``。 在完整的
    套件下，另一个测试会留下一个 stray package directory (
    ``.../site-packages/browser_use``) 在
    ``sys.path[0]``，这使得其子包可以作为顶层模块导入 — ``browser_use/mcp`` 然后遮住
    了真正的 ``mcp`` 和 FastMCP
    的 eager ``import mcp`` 在启动时会因为一个 ``mcp`` <-> ``browser_use.mcp`` 的循环
    导入而崩溃。 删除此类条目将
    恢复正常的顶级分辨率。
    """
    cleaned = [
        entry
        for entry in sys.path
        if os.path.basename(os.path.dirname(entry.rstrip(os.sep))) != "site-packages"
    ]
    sys.path[:] = cleaned


def run_agent_server(port, api_key):
    _drop_site_packages_subdir_paths()

    # 为服务器进程配置身份验证。
    #
    # 使用 V1 索引环境变量和旧版 V0 变量来保持此测试在不同的配置解析行为中保持稳定。
    #
    os.environ["OH_SESSION_API_KEYS_0"] = api_key
    os.environ["SESSION_API_KEY"] = api_key
    sys.argv = ["agent-server", "--port", str(port)]
    from openhands.agent_server.__main__ import main

    main()


def _terminate(process):
    process.terminate()
    process.join(timeout=5)
    if process.is_alive():
        process.kill()
        process.join()


def _wait_until_ready(process, port, timeout=30.0):
    """轮询轻量级 /alive 端点直到服务器响应。

    服务器进程退出后立即返回 False（而不是阻塞整个超时），因此可以在新端口上重试失败
    的端口绑定。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not process.is_alive():
            return False
        try:
            response = requests.get(f"http://127.0.0.1:{port}/alive", timeout=1)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def agent_server():
    api_key = "test-wsproto-key"
    ctx = multiprocessing.get_context("spawn")

    # find_free_port() 在服务器重新绑定它之前关闭了套接字，留下了一个TOCTOU窗口，另一个
    # 在繁忙的CI主机上的进程可以窃取端口并导致启动失败。 重试在一个新鲜的端口上吸收那场
    # 比赛。
    #
    process = None
    port = None
    for _ in range(3):
        port = find_free_port()
        process = ctx.Process(target=run_agent_server, args=(port, api_key))
        process.start()
        if _wait_until_ready(process, port):
            break
        _terminate(process)
    else:
        pytest.fail("Agent server failed to start after multiple attempts")

    yield {"port": port, "api_key": api_key}

    _terminate(process)


def test_agent_server_starts_with_wsproto(agent_server):
    response = requests.get(f"http://127.0.0.1:{agent_server['port']}/docs")
    assert response.status_code == 200
    assert (
        "OpenHands Agent Server" in response.text or "swagger" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_agent_server_websocket_with_wsproto(agent_server):
    port = agent_server["port"]
    api_key = agent_server["api_key"]

    response = requests.post(
        f"http://127.0.0.1:{port}/api/conversations",
        headers={"X-Session-API-Key": api_key},
        json={
            "agent": {
                "kind": "Agent",
                "llm": {
                    "usage_id": "test-llm",
                    "model": "test-provider/test-model",
                    "api_key": "test-key",
                },
                "tools": [],
            },
            "workspace": {"working_dir": "/tmp/test-workspace"},
        },
    )
    assert response.status_code in [200, 201]
    conversation_id = response.json()["id"]

    ws_url = (
        f"ws://127.0.0.1:{port}/sockets/events/{conversation_id}"
        f"?session_api_key={api_key}&resend_all=true"
    )

    async with websockets.connect(ws_url, open_timeout=5) as ws:
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=2)
            assert response is not None
        except TimeoutError:
            pass

        await ws.send(
            json.dumps({"role": "user", "content": "Hello from wsproto test"})
        )


@pytest.mark.asyncio
async def test_agent_server_websocket_with_wsproto_header_auth(agent_server):
    port = agent_server["port"]
    api_key = agent_server["api_key"]

    response = requests.post(
        f"http://127.0.0.1:{port}/api/conversations",
        headers={"X-Session-API-Key": api_key},
        json={
            "agent": {
                "kind": "Agent",
                "llm": {
                    "usage_id": "test-llm",
                    "model": "test-provider/test-model",
                    "api_key": "test-key",
                },
                "tools": [],
            },
            "workspace": {"working_dir": "/tmp/test-workspace"},
        },
    )
    assert response.status_code in [200, 201]
    conversation_id = response.json()["id"]

    ws_url = f"ws://127.0.0.1:{port}/sockets/events/{conversation_id}?resend_all=true"

    async with websockets.connect(
        ws_url,
        open_timeout=5,
        additional_headers={"X-Session-API-Key": api_key},
    ) as ws:
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=2)
            assert response is not None
        except TimeoutError:
            pass

        await ws.send(
            json.dumps(
                {"role": "user", "content": "Hello from wsproto header auth test"}
            )
        )


@pytest.mark.asyncio
async def test_agent_server_websocket_first_message_auth_accepted(agent_server):
    """第一消息身份验证：不使用查询/标头密钥进行连接，通过第一帧进行身份验证。

    测试了实 WebSocket 协议切换（握手 → 消费第一个帧作为认证 → 继续正常消息流） 模拟
    对象只能覆盖的实操。 请参阅 PR 审查有关测试覆盖率差距的反馈。
    """
    port = agent_server["port"]
    api_key = agent_server["api_key"]

    response = requests.post(
        f"http://127.0.0.1:{port}/api/conversations",
        headers={"X-Session-API-Key": api_key},
        json={
            "agent": {
                "kind": "Agent",
                "llm": {
                    "usage_id": "test-llm",
                    "model": "test-provider/test-model",
                    "api_key": "test-key",
                },
                "tools": [],
            },
            "workspace": {"working_dir": "/tmp/test-workspace"},
        },
    )
    assert response.status_code in [200, 201]
    conversation_id = response.json()["id"]

    # URL 或标头中没有 session_api_key — 必须通过第一帧进行身份验证。
    ws_url = f"ws://127.0.0.1:{port}/sockets/events/{conversation_id}?resend_all=true"

    async with websockets.connect(ws_url, open_timeout=5) as ws:
        # 将身份验证帧作为握手后的第一条消息发送。
        await ws.send(json.dumps({"type": "auth", "session_api_key": api_key}))

        # 连接必须保持可用：尝试接收（对于空对话，resend_all 可能不会产生任何结果，因此
        # 这里的超时就可以了）。
        #
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=2)
            assert response is not None
        except TimeoutError:
            pass

        # 后续消息必须作为消息（而不是身份验证）进行处理 - 证明身份验证帧是由身份验证处
        # 理程序而不是主循环消耗的。
        #
        await ws.send(
            json.dumps({"role": "user", "content": "Hello after first-message auth"})
        )


@pytest.mark.asyncio
async def test_agent_server_websocket_first_message_auth_rejected(agent_server):
    """第一条消息身份验证：无效按键触发 WebSocket 关闭，代码为 4001。"""
    port = agent_server["port"]

    # 不需要对话——身份验证拒绝发生在对话查找之前。
    ws_url = f"ws://127.0.0.1:{port}/sockets/events/{uuid4()}"

    async with websockets.connect(ws_url, open_timeout=5) as ws:
        # 发送无效的第一条消息验证帧。
        await ws.send(
            json.dumps({"type": "auth", "session_api_key": "definitely-wrong-key"})
        )

        # 服务器必须关闭连接并返回代码 4001（“身份验证失败”）。 在关闭的套接字上接收会引
        # 发 ConnectionClosed。
        #
        with pytest.raises(websockets.exceptions.ConnectionClosed) as exc_info:
            await asyncio.wait_for(ws.recv(), timeout=5)

    assert exc_info.value.rcvd is not None
    assert exc_info.value.rcvd.code == 4001


@pytest.mark.asyncio
async def test_agent_server_websocket_first_message_auth_malformed(agent_server):
    """第一条消息身份验证：格式错误 JSON 触发关闭并显示代码 4001。"""
    port = agent_server["port"]

    ws_url = f"ws://127.0.0.1:{port}/sockets/events/{uuid4()}"

    async with websockets.connect(ws_url, open_timeout=5) as ws:
        # 发送无效的 JSON 作为第一帧。
        await ws.send("this is not json")

        with pytest.raises(websockets.exceptions.ConnectionClosed) as exc_info:
            await asyncio.wait_for(ws.recv(), timeout=5)

    assert exc_info.value.rcvd is not None
    assert exc_info.value.rcvd.code == 4001


# /sockets/session/{id}. 单元测试独立地涵盖了作者、订阅者和重放； 那里没有任何东西执行端
# 点。 这些驱动它端到端：验证、查找、同步帧、从磁盘重播、通过光标恢复、关闭代码。
#


def _create_conversation(port: int, api_key: str) -> str:
    response = requests.post(
        f"http://127.0.0.1:{port}/api/conversations",
        headers={"X-Session-API-Key": api_key},
        json={
            "agent": {
                "kind": "Agent",
                "llm": {
                    "usage_id": "test-llm",
                    "model": "test-provider/test-model",
                    "api_key": "test-key",
                },
                "tools": [],
            },
            "workspace": {"working_dir": "/tmp/test-workspace"},
        },
    )
    assert response.status_code in [200, 201], response.text
    return response.json()["id"]


async def _collect_frames(ws, *, until=None, seconds: float = 15.0) -> list[dict]:
    """读取帧直到满足 ``until`` 或超过截止日期。

    智能体步骤失败（没有真正的LLM在``test-provider``后面），因此帧序列不固定，有趣帧
    很少是第一个——瞬态快照立即到来，持久事件随后。 等待谓词而不是
    安静期可以避免成为一场竞赛。
    """
    frames: list[dict] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=deadline - loop.time())
        except TimeoutError:
            break
        except websockets.exceptions.ConnectionClosed:
            break
        frames.append(json.loads(raw))
        if until is not None and any(until(f) for f in frames):
            break
    return frames


def _is_durable(frame: dict) -> bool:
    return frame["type"] == "durable"


@pytest.mark.asyncio
async def test_session_socket_opens_with_a_sync_frame(agent_server):
    """第一帧始终为 ``sync``。"""
    port, api_key = agent_server["port"], agent_server["api_key"]
    conversation_id = _create_conversation(port, api_key)

    ws_url = (
        f"ws://127.0.0.1:{port}/sockets/session/{conversation_id}"
        f"?session_api_key={api_key}"
    )
    async with websockets.connect(ws_url, open_timeout=5) as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))

    assert first["type"] == "sync"
    # 没有提出任何要求，因此范围在底部开放。
    assert first.get("from_seq") is None


@pytest.mark.asyncio
async def test_session_socket_durable_frame_carries_seq_over_the_wire(agent_server):
    """在套接字上发送的消息作为带有 seq 的持久帧返回。

    端点的要点：一个``Event``在一个信封内，带有可恢复的序列号，通过真实服务器。
    """
    port, api_key = agent_server["port"], agent_server["api_key"]
    conversation_id = _create_conversation(port, api_key)

    ws_url = (
        f"ws://127.0.0.1:{port}/sockets/session/{conversation_id}"
        f"?session_api_key={api_key}"
    )
    async with websockets.connect(ws_url, open_timeout=5) as ws:
        assert (
            json.loads(await asyncio.wait_for(ws.recv(), timeout=5))["type"] == "sync"
        )
        await ws.send(json.dumps({"role": "user", "content": "hello session socket"}))
        frames = await _collect_frames(ws, until=_is_durable)

    durable = [f for f in frames if f["type"] == "durable"]
    assert durable, f"no durable frame arrived; got {[f['type'] for f in frames]}"
    # seq 是实数且单调的； 载荷是未触及的事件。
    seqs = [f["seq"] for f in durable]
    assert all(isinstance(s, int) for s in seqs)
    assert seqs == sorted(seqs)
    assert all("kind" in f["event"] and "id" in f["event"] for f in durable)
    # subscribe 上推送的快照不携带 seq。
    assert all("seq" not in f for f in frames if f["type"] == "transient")


@pytest.mark.asyncio
async def test_session_socket_resumes_history_with_after_seq(agent_server):
    """重新连接 ``after_seq`` 会从磁盘重播并且不会丢失任何内容。"""
    port, api_key = agent_server["port"], agent_server["api_key"]
    conversation_id = _create_conversation(port, api_key)

    base_url = (
        f"ws://127.0.0.1:{port}/sockets/session/{conversation_id}"
        f"?session_api_key={api_key}"
    )

    # 产生一些历史。
    async with websockets.connect(base_url, open_timeout=5) as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)  # 同步
        await ws.send(json.dumps({"role": "user", "content": "first message"}))
        first_pass = await _collect_frames(ws, until=_is_durable)

    produced = [f["seq"] for f in first_pass if f["type"] == "durable"]
    assert produced, "expected the first connection to persist something"

    # after_seq=-1 means "from the start".
    async with websockets.connect(f"{base_url}&after_seq=-1", open_timeout=5) as ws:
        sync = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        replayed = await _collect_frames(ws, until=_is_durable)

    assert sync["type"] == "sync"
    assert sync["from_seq"] == -1
    assert sync["through_seq"] >= max(produced)

    replayed_seqs = [f["seq"] for f in replayed if f["type"] == "durable"]
    # 从头开始并涵盖第一遍看到的内容。
    assert replayed_seqs[:1] == [0]
    assert set(produced).issubset(set(replayed_seqs))
    # 重播/现场接缝中没有任何两次。
    assert len(replayed_seqs) == len(set(replayed_seqs))


@pytest.mark.asyncio
async def test_session_socket_unknown_conversation_closes_4004(agent_server):
    port, api_key = agent_server["port"], agent_server["api_key"]

    ws_url = (
        f"ws://127.0.0.1:{port}/sockets/session/{uuid4()}?session_api_key={api_key}"
    )
    async with websockets.connect(ws_url, open_timeout=5) as ws:
        with pytest.raises(websockets.exceptions.ConnectionClosed) as exc_info:
            await asyncio.wait_for(ws.recv(), timeout=5)

    assert exc_info.value.rcvd is not None
    assert exc_info.value.rcvd.code == 4004


@pytest.mark.asyncio
async def test_session_socket_survives_a_malformed_inbound_frame(agent_server):
    """垃圾帧会产生错误帧； 连接保持可用。"""
    port, api_key = agent_server["port"], agent_server["api_key"]
    conversation_id = _create_conversation(port, api_key)

    ws_url = (
        f"ws://127.0.0.1:{port}/sockets/session/{conversation_id}"
        f"?session_api_key={api_key}"
    )
    async with websockets.connect(ws_url, open_timeout=5) as ws:
        assert (
            json.loads(await asyncio.wait_for(ws.recv(), timeout=5))["type"] == "sync"
        )

        await ws.send("this is not json")
        frames = await _collect_frames(ws, until=lambda f: f["type"] == "error")
        errors = [f for f in frames if f["type"] == "error"]
        assert errors, f"expected an error frame; got {[f['type'] for f in frames]}"

        # 仍然存活：格式正确的消息仍在处理。
        await ws.send(json.dumps({"role": "user", "content": "still here"}))
        after = await _collect_frames(ws, until=_is_durable)
        assert any(f["type"] == "durable" for f in after)
