"""测试 ``notifications/tools/list_changed`` 处理。

一些 MCP 服务器 (e.g. Datadog 的托管 MCP 服务器）使用渐进式
disclosure: 他们在连接时公开一个小型网关工具集并注册
仅在调用技能加载工具后才使用其他工具，并用 ``notifications/tools/list_changed`` 表示
更改。 这些测试验证了
``create_mcp_tools`` 订阅该通知，重新列出工具，并使用新添加的工具调用
``on_tools_changed`` 回调。

通过流式传输 HTTP 进行的端到端通知传递针对下面的真实 FastMCP 服务器进行。 因为要在会
话中可靠地交付服务器发起的通知，需要服务器保持SSE通知流的打开（Dat
adog托管服务器的方式），核心的diff/refresh逻辑还被专注于单元测试的逻辑覆盖，这些逻辑
不依赖于传输层的时间。
"""

import asyncio
import socket
import threading
import time
from typing import cast

import mcp.types as mcp_types
import pytest
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_context
from pydantic import SecretStr, ValidationError

from openhands.sdk.agent import Agent
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.llm import LLM, TextContent
from openhands.sdk.mcp import MCPClient, create_mcp_tools
from openhands.sdk.mcp.config import coerce_mcp_config
from openhands.sdk.mcp.tool import MCPToolDefinition
from openhands.sdk.mcp.utils import (
    _refresh_tools,
    _ToolListChangedHandler,
)


def _native_config(raw: dict) -> dict:
    """将 FastMCP 形状的配置字典强制转换为原生 ``dict[str, MCPServer]``。"""
    return coerce_mcp_config(raw)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    import httpx

    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/mcp"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=1.0) as client:
                client.get(url)
            return
        except Exception as e:  # noqa: BLE001
            last_error = e
            time.sleep(0.1)
    raise RuntimeError(f"MCP test server on port {port} did not start: {last_error}")


def _make_mcp_tool(name: str) -> mcp_types.Tool:
    return mcp_types.Tool(
        name=name,
        description=f"tool {name}",
        inputSchema={"type": "object", "properties": {}},
    )


class _FakeClient:
    """``_refresh_tools`` 使用 ``MCPClient`` 的最小替代。

    ``_refresh_tools`` 只需要 ``list_tools()`` (异步) 并且
    ``_tools`` / ``_closed`` 属性，因此轻量级的 fake 可以保持 diff 逻辑单元可测试，而
    无需启动真实服务器。
    """

    def __init__(self, tools: list[mcp_types.Tool]):
        self._server_tools = list(tools)
        self._tools: list[MCPToolDefinition] = []
        self._closed = False
        self._tools_reconciled_callback = None

    async def list_tools(self) -> list[mcp_types.Tool]:
        return list(self._server_tools)


class _ConcreteAgent(AgentBase):
    """用于单元测试运行时助手的最小具体 ``AgentBase``。

    ``AgentBase`` 是抽象的 (``step``) 和冻结的 Pydantic 模型，因此仅执行运行时工具更
    新的测试使用此存根来绕过完整的智能体构造。
    """

    def __init__(self, _initialized: bool, _tools):  # noqa: ANN001
        # 跳过Pydantic验证； 设置助手读取的属性。
        object.__setattr__(self, "_initialized", _initialized)
        object.__setattr__(self, "_tools", _tools)
        object.__setattr__(self, "_tools_lock", threading.RLock())
        object.__setattr__(self, "filter_tools_regex", None)

    def step(self, conversation, on_event, on_token=None):  # noqa: ARG002, ANN001
        raise NotImplementedError


def test_refresh_tools_reports_only_new_tools():
    """``_refresh_tools`` 与现有工具的差异和报告的补充。"""
    client = _FakeClient([_make_mcp_tool("a"), _make_mcp_tool("b")])
    # 模拟已发现的先前连接 ``a``。
    client._tools = list(
        MCPToolDefinition.create(mcp_tool=_make_mcp_tool("a"), mcp_client=client)  # type: ignore[arg-type]
    )

    received: list[list[str]] = []

    async def run():
        await _refresh_tools(
            client,  # type: ignore[arg-type]
            on_tools_changed=lambda tools: received.append([t.name for t in tools]),
        )

    asyncio.new_event_loop().run_until_complete(run())

    assert {t.name for t in client._tools} == {"a", "b"}
    assert received == [["b"]]


def test_refresh_tools_drops_removed_tools():
    """服务器不再通告的工具将从客户端删除。"""
    client = _FakeClient([_make_mcp_tool("a")])
    client._tools = list(
        MCPToolDefinition.create(mcp_tool=_make_mcp_tool("a"), mcp_client=client)  # type: ignore[arg-type]
    ) + list(
        MCPToolDefinition.create(mcp_tool=_make_mcp_tool("gone"), mcp_client=client)  # type: ignore[arg-type]
    )

    async def run():
        await _refresh_tools(client, on_tools_changed=None)  # type: ignore[arg-type]

    asyncio.new_event_loop().run_until_complete(run())

    assert {t.name for t in client._tools} == {"a"}


def test_refresh_tools_reconciles_updates_and_removals():
    """完整快照回调接收更新的定义和删除。"""
    old_tool = mcp_types.Tool(
        name="changing",
        description="old schema",
        inputSchema={
            "type": "object",
            "properties": {"old": {"type": "string"}},
            "required": ["old"],
        },
    )
    new_tool = mcp_types.Tool(
        name="changing",
        description="new schema",
        inputSchema={
            "type": "object",
            "properties": {"new": {"type": "integer"}},
            "required": ["new"],
        },
    )
    client = _FakeClient([new_tool])
    old_definition = MCPToolDefinition.create(
        mcp_tool=old_tool,
        mcp_client=cast(MCPClient, client),
    )[0]
    old_definition.action_from_arguments({"old": "value"})
    client._tools = [
        old_definition,
        MCPToolDefinition.create(
            mcp_tool=_make_mcp_tool("gone"),
            mcp_client=cast(MCPClient, client),
        )[0],
    ]
    received: list[tuple[object, list[MCPToolDefinition]]] = []

    async def run():
        await _refresh_tools(
            cast(MCPClient, client),
            on_tools_reconciled=lambda owner, tools: received.append(
                (owner, list(tools))
            ),
        )

    asyncio.new_event_loop().run_until_complete(run())

    assert len(received) == 1
    owner, tools = received[0]
    assert owner is client
    assert [tool.name for tool in tools] == ["changing"]
    assert tools[0].description == "new schema"
    tools[0].action_from_arguments({"new": 42})
    with pytest.raises(ValidationError):
        tools[0].action_from_arguments({"old": "value"})


def test_refresh_tools_no_callback_still_reconciles():
    """如果没有回调，客户端工具列表仍保留在同步中。"""
    client = _FakeClient([_make_mcp_tool("a"), _make_mcp_tool("b")])

    async def run():
        await _refresh_tools(client, on_tools_changed=None)  # type: ignore[arg-type]

    asyncio.new_event_loop().run_until_complete(run())

    assert {t.name for t in client._tools} == {"a", "b"}


def test_handler_invokes_refresh_on_list_changed():
    """``_ToolListChangedHandler`` 重新列出并根据通知回电。"""
    client = _FakeClient([_make_mcp_tool("a"), _make_mcp_tool("b")])
    client._tools = list(
        MCPToolDefinition.create(mcp_tool=_make_mcp_tool("a"), mcp_client=client)  # type: ignore[arg-type]
    )
    received: list[list[str]] = []
    handler = _ToolListChangedHandler(
        client=client,  # type: ignore[arg-type]
        on_tools_changed=lambda tools: received.append([t.name for t in tools]),
    )

    async def run():
        await handler.on_tool_list_changed(mcp_types.ToolListChangedNotification())
        deadline = time.time() + 1.0
        while time.time() < deadline and not received:
            await asyncio.sleep(0.01)

    asyncio.new_event_loop().run_until_complete(run())

    assert {t.name for t in client._tools} == {"a", "b"}
    assert received == [["b"]]


def test_handler_skips_when_client_closed():
    """关闭后到达的通知将被忽略。"""
    client = _FakeClient([_make_mcp_tool("a")])
    client._closed = True
    handler = _ToolListChangedHandler(
        client=client,  # type: ignore[arg-type]
        on_tools_changed=lambda tools: None,
    )

    asyncio.new_event_loop().run_until_complete(
        handler.on_tool_list_changed(mcp_types.ToolListChangedNotification())
    )

    assert client._tools == []


@pytest.fixture
def progressive_server():
    """添加工具并发送 ``tools/list_changed`` 的 MCP 服务器。

    调用 ``register_extra_tool`` 添加第二个工具并发送
    ``notifications/tools/list_changed`` 向当前会话发出通知，模仿 Datadog 的渐进式披
    露行为。
    """
    mcp = FastMCP("progressive-test-server")

    async def notify_list_changed() -> None:
        notification = mcp_types.ToolListChangedNotification()
        loop = asyncio.get_running_loop()
        loop.create_task(get_context().send_notification(notification))

    @mcp.tool()
    async def gateway() -> str:
        """始终可用的网关工具。"""
        return "gateway-ok"

    @mcp.tool()
    async def register_extra_tool() -> str:
        """注册第二个工具并通知客户端列表已更改。"""

        @mcp.tool()
        def extra(value: int) -> int:
            """客户端连接后添加的工具。"""
            return value * 2

        # 将通知作为即发即忘任务发送，以便首先刷新工具调用响应； 通知通过客户端为服务器
        # 通知保持打开的长期 SSE 流。
        #
        await notify_list_changed()
        return "registered"

    @mcp.tool()
    async def remove_extra_tool() -> str:
        """删除动态注册的工具并通知客户端。"""
        mcp.local_provider.remove_tool("extra")
        await notify_list_changed()
        return "removed"

    port = _find_free_port()

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            mcp.run_http_async(
                host="127.0.0.1",
                port=port,
                transport="http",
                show_banner=False,
                path="/mcp",
            )
        )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    _wait_for_port(port)
    yield port


def test_no_callback_still_connects(progressive_server: int):
    """``on_tools_changed=None`` 不得破坏工具创建。"""
    port = progressive_server
    config = _native_config(
        {
            "mcpServers": {
                "progressive": {
                    "transport": "http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                }
            }
        }
    )
    with create_mcp_tools(config, timeout=10.0) as client:
        names = {t.name for t in client}
        assert "gateway" in names
        assert "register_extra_tool" in names


def test_default_provider_wires_on_tools_reconciled_before_connect(
    progressive_server: int,
):
    """DefaultMCPToolProvider 必须将 on_tools_reconciled 转发至
    create_mcp_tools 于是，它在客户端连接之前就附上了，而不是在客户端返回create_tools
    之后就设置（这将丢弃在初始连接期间到达的通知）。
    """
    from openhands.sdk.mcp.utils import DefaultMCPToolProvider

    port = progressive_server
    config = _native_config(
        {
            "mcpServers": {
                "progressive": {
                    "transport": "http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                }
            }
        }
    )

    def on_tools_reconciled(client, tools):  # noqa: ANN001
        pass

    client = DefaultMCPToolProvider().create_tools(
        config, timeout=10.0, on_tools_reconciled=on_tools_reconciled
    )
    try:
        assert client._tools_reconciled_callback is on_tools_reconciled
    finally:
        client.sync_close()


def test_list_changed_notification_reconciles_readded_agent_tool(
    progressive_server: int,
):
    """重新添加的工具取代了智能体的过时 MCP 定义。"""
    port = progressive_server
    config = _native_config(
        {
            "mcpServers": {
                "progressive": {
                    "transport": "http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                }
            }
        }
    )
    received: list[str] = []
    agent = _ConcreteAgent(_initialized=True, _tools={})

    def on_tools_changed(tools):  # noqa: ANN001
        received.extend(tool.name for tool in tools)

    def on_tools_reconciled(client, tools):  # noqa: ANN001
        agent._on_mcp_tools_reconciled(client, tools)

    with create_mcp_tools(
        config,
        timeout=10.0,
        on_tools_changed=on_tools_changed,
        on_tools_reconciled=on_tools_reconciled,
    ) as client:
        agent.add_runtime_tools(client.tools)
        initial_names = {t.name for t in client.tools}
        assert "gateway" in initial_names
        assert "register_extra_tool" in initial_names
        assert "remove_extra_tool" in initial_names
        assert "extra" not in initial_names

        register_tool = next(t for t in client.tools if t.name == "register_extra_tool")
        register_observation = register_tool(register_tool.action_from_arguments({}))
        assert not register_observation.is_error

        deadline = time.time() + 10.0
        current_names = {t.name for t in client.tools}
        while time.time() < deadline and "extra" not in current_names:
            time.sleep(0.1)
            current_names = {t.name for t in client.tools}

        assert "extra" in current_names
        assert received == ["extra"]

        extra_tool = next(t for t in client.tools if t.name == "extra")
        extra_observation = extra_tool(extra_tool.action_from_arguments({"value": 21}))
        extra_text = "\n".join(
            block.text
            for block in extra_observation.content
            if isinstance(block, TextContent)
        )
        assert not extra_observation.is_error
        assert "42" in extra_text

        first_agent_extra = agent.tools_map["extra"]
        remove_tool = next(t for t in client.tools if t.name == "remove_extra_tool")
        remove_observation = remove_tool(remove_tool.action_from_arguments({}))
        assert not remove_observation.is_error

        deadline = time.time() + 10.0
        while time.time() < deadline and any(
            tool.name == "extra" for tool in client.tools
        ):
            time.sleep(0.1)

        assert all(tool.name != "extra" for tool in client.tools)
        assert "extra" not in agent.tools_map

        register_observation = register_tool(register_tool.action_from_arguments({}))
        assert not register_observation.is_error

        deadline = time.time() + 10.0
        while time.time() < deadline and "extra" not in agent.tools_map:
            time.sleep(0.1)

        readded_agent_extra = agent.tools_map["extra"]
        readded_client_extra = next(t for t in client.tools if t.name == "extra")
        assert readded_agent_extra is readded_client_extra
        assert readded_agent_extra is not first_agent_extra
        assert received == ["extra", "extra"]

        readded_observation = readded_agent_extra(
            readded_agent_extra.action_from_arguments({"value": 21})
        )
        assert not readded_observation.is_error


def test_on_mcp_tools_changed_registers_runtime_tools():
    """``AgentBase._on_mcp_tools_changed`` 转发至 ``add_runtime_tools``。"""
    agent = _ConcreteAgent(_initialized=True, _tools={})
    client = _FakeClient([])
    tool = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("dynamic"),
        mcp_client=cast(MCPClient, client),
    )[0]

    agent._on_mcp_tools_changed([tool])

    assert agent.tools_map["dynamic"] is tool


def test_add_runtime_tools_does_not_leak_into_model_copy():
    """在复制的智能体上注册工具不得改变原始工具。

    Agent.model_copy() 通过引用共享私有属性对象 (e.g._tools)，因此就地改变工具映射会
    在副本之间泄漏。
    """
    original = Agent(llm=LLM(model="test-model", api_key=SecretStr("k")), tools=[])
    original._initialized = True
    copy = original.model_copy()
    client = _FakeClient([])
    tool = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("dynamic"),
        mcp_client=cast(MCPClient, client),
    )[0]

    copy.add_runtime_tools([tool])

    assert "dynamic" in copy.tools_map
    assert "dynamic" not in original.tools_map


def test_add_runtime_tools_tolerates_notification_installed_before_return():
    """通过协调回调在连接中安装的工具不得
    与调用者自己的 add_runtime_tools() 调用发生冲突。

    如果通知/工具/list_changed 到达时，初始工具/请求仍在飞行中 on_tools_changed 可以
    使用这个相同的工具进行安装 MCPClient 之
    前 create_tools() 返回。 调用者（e.g. LocalConversation._ensure_agent_ready然后调
    用
    add_runtime_tools() 用客户端返回的快照，该快照已经包含了那个工具； 这必须被视为刷
    新而不是重复工具冲突。
    """
    agent = _ConcreteAgent(_initialized=True, _tools={})
    client = _FakeClient([])
    tool = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("only_tool"),
        mcp_client=cast(MCPClient, client),
    )[0]

    # 模拟在 create_tools() 返回之前安装工具的飞行中 on_tools_changed 回调。
    #
    agent._on_mcp_tools_changed([tool])

    # 使用客户端返回的快照模拟调用者的 add_runtime_tools() 调用，该快照已包含相同的工具
    # 。
    #
    agent.add_runtime_tools([tool])

    assert agent.tools_map["only_tool"] is tool


def test_on_mcp_tools_changed_skips_when_not_initialized():
    """在初始化之前，通知会被丢弃，而不是崩溃。"""
    agent = _ConcreteAgent(_initialized=False, _tools=None)

    # 即使 add_runtime_tools 会发出警告，也不能加注。
    agent._on_mcp_tools_changed([])  # type: ignore[arg-type]


def test_on_mcp_tools_reconciled_does_not_remove_other_client_tools():
    """客户端快照仅替换该客户端拥有的工具。"""
    first_client = _FakeClient([])
    second_client = _FakeClient([])
    first_tool = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("first"),
        mcp_client=cast(MCPClient, first_client),
    )[0]
    second_tool = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("second"),
        mcp_client=cast(MCPClient, second_client),
    )[0]
    replacement = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("replacement"),
        mcp_client=cast(MCPClient, first_client),
    )[0]
    agent = _ConcreteAgent(
        _initialized=True,
        _tools={"first": first_tool, "second": second_tool},
    )

    agent._on_mcp_tools_reconciled(
        cast(MCPClient, first_client),
        [replacement],
    )

    assert set(agent.tools_map) == {"replacement", "second"}
    assert agent.tools_map["second"] is second_tool


def test_on_mcp_tools_reconciled_filters_before_conflict_check():
    first_client = _FakeClient([])
    second_client = _FakeClient([])
    blocked = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("blocked"),
        mcp_client=cast(MCPClient, first_client),
    )[0]
    filtered_conflict = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("blocked"),
        mcp_client=cast(MCPClient, second_client),
    )[0]
    allowed = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("allowed"),
        mcp_client=cast(MCPClient, second_client),
    )[0]
    agent = _ConcreteAgent(_initialized=True, _tools={"blocked": blocked})
    object.__setattr__(agent, "filter_tools_regex", r"^allowed$")

    agent._on_mcp_tools_reconciled(
        cast(MCPClient, second_client),
        [filtered_conflict, allowed],
    )

    assert set(agent.tools_map) == {"blocked", "allowed"}


def test_on_mcp_tools_reconciled_serializes_client_updates():
    first_snapshot = threading.Event()
    second_snapshot = threading.Event()

    class CoordinatedDict(dict[str, MCPToolDefinition]):
        def __init__(self, values: dict[str, MCPToolDefinition]):
            super().__init__(values)
            self.local = threading.local()

        def items(self):  # type: ignore[override]  # noqa: ANN201
            snapshot = list(super().items())
            count = getattr(self.local, "count", 0) + 1
            self.local.count = count
            if count == 2:
                if first_snapshot.is_set():
                    second_snapshot.set()
                else:
                    first_snapshot.set()
                    second_snapshot.wait(0.2)
            return snapshot

    first_client = _FakeClient([])
    second_client = _FakeClient([])
    first_old = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("first_old"),
        mcp_client=cast(MCPClient, first_client),
    )[0]
    second_old = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("second_old"),
        mcp_client=cast(MCPClient, second_client),
    )[0]
    first_new = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("first_new"),
        mcp_client=cast(MCPClient, first_client),
    )[0]
    second_new = MCPToolDefinition.create(
        mcp_tool=_make_mcp_tool("second_new"),
        mcp_client=cast(MCPClient, second_client),
    )[0]
    agent = _ConcreteAgent(
        _initialized=True,
        _tools=CoordinatedDict({"first_old": first_old, "second_old": second_old}),
    )
    threads = [
        threading.Thread(
            target=agent._on_mcp_tools_reconciled,
            args=(cast(MCPClient, first_client), [first_new]),
        ),
        threading.Thread(
            target=agent._on_mcp_tools_reconciled,
            args=(cast(MCPClient, second_client), [second_new]),
        ),
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert set(agent.tools_map) == {"first_new", "second_new"}
