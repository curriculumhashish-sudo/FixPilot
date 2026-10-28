"""测试 BrowserToolSet 功能。"""

import json
import logging
import tempfile
import threading
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event import Event, SystemPromptEvent
from openhands.sdk.llm import LLM
from openhands.sdk.tool import Tool, ToolDefinition
from openhands.sdk.tool.registry import resolve_tool
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.browser_use import BrowserToolSet
from openhands.tools.browser_use.definition import BROWSER_PROMPT_GUIDANCE
from openhands.tools.browser_use.impl import BrowserToolExecutor


@pytest.fixture(autouse=True)
def _reset_shared_executor():
    """在每次测试之前和之后重置共享执行器单例。"""
    BrowserToolSet._shared_executor = None
    yield
    if BrowserToolSet._shared_executor is not None:
        BrowserToolSet._shared_executor.close()
    BrowserToolSet._shared_executor = None


@pytest.fixture(autouse=True)
def _mock_browser_executor_init():
    def fake_init(self, **_kwargs):
        self.full_output_save_dir = None
        self._initialized = False
        # 工具集测试从不分配浏览器资源； 保持 close() 为空操作。
        self._cleanup_initiated = True
        self._close_lock = threading.Lock()
        self._action_timeout_seconds = 30.0
        self._async_executor = MagicMock()
        self._async_executor.close = MagicMock()

    with (
        patch.object(BrowserToolExecutor, "__init__", fake_init),
        patch.object(
            BrowserToolExecutor,
            "_ensure_chromium_available",
            return_value="/usr/bin/chromium",
        ),
    ):
        yield


def _create_test_conv_state(temp_dir: str) -> ConversationState:
    """创建测试对话状态的帮助程序。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return ConversationState.create(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=temp_dir),
    )


def test_browser_toolset_create_returns_list():
    """测试 BrowserToolSet.create() 返回工具列表。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = BrowserToolSet.create(conv_state=conv_state)

        assert isinstance(tools, list)
        assert len(tools) == 14  # 所有浏览器工具（包括录音工具）

        # 验证所有项目都是工具实例
        for tool in tools:
            assert isinstance(tool, ToolDefinition)


def test_browser_toolset_create_includes_all_browser_tools():
    """测试 BrowserToolSet.create() 是否包含所有预期的浏览器工具。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = BrowserToolSet.create(conv_state=conv_state)

        # 获取工具名称
        tool_names = [tool.name for tool in tools]

        # 基于浏览器工具的预期工具名称
        expected_names = [
            "browser_navigate",
            "browser_click",
            "browser_get_state",
            "browser_get_content",
            "browser_type",
            "browser_scroll",
            "browser_go_back",
            "browser_list_tabs",
            "browser_switch_tab",
            "browser_close_tab",
            "browser_get_storage",
            "browser_set_storage",
            "browser_start_recording",
            "browser_stop_recording",
        ]

        # 验证所有预期的工具是否存在
        for expected_name in expected_names:
            assert expected_name in tool_names, f"Missing tool: {expected_name}"

        # 确认没有额外的工具
        assert len(tool_names) == len(expected_names)


def test_browser_toolset_create_tools_have_shared_executor():
    """测试 BrowserToolSet.create() 中的所有工具是否共享相同的执行器。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = BrowserToolSet.create(conv_state=conv_state)

        # 从第一个工具中获取执行器
        first_executor = tools[0].executor
        assert first_executor is not None
        assert isinstance(first_executor, BrowserToolExecutor)

        # 验证所有工具共享相同的执行器实例
        for tool in tools:
            assert tool.executor is first_executor


def test_browser_toolset_create_tools_are_properly_configured():
    """测试 BrowserToolSet.create() 中的工具是否已正确配置。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = BrowserToolSet.create(conv_state=conv_state)

        # 查找要测试的特定工具（e.g.，导航工具）
        navigate_tool = None
        for tool in tools:
            if tool.name == "browser_navigate":
                navigate_tool = tool
                break

        assert navigate_tool is not None
        assert navigate_tool.description is not None
        assert navigate_tool.action_type is not None
        assert navigate_tool.observation_type is not None
        assert navigate_tool.executor is not None


def test_browser_toolset_create_multiple_calls_share_executor():
    """测试对 BrowserToolSet.create() 的多个调用是否共享同一个执行器。

    这对于子智能体支持至关重要：子智能体独立地调用BrowserToolSet.create()，但必须重用
    父进程的执行器以避免CDP端口冲突，当多个Chromium实
    例尝试在沙箱容器中绑定相同的调试端口时。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools1 = BrowserToolSet.create(conv_state=conv_state)
        tools2 = BrowserToolSet.create(conv_state=conv_state)

        executor1 = tools1[0].executor
        executor2 = tools2[0].executor

        # 执行器必须是同一个实例（共享单例）
        assert executor1 is executor2
        assert isinstance(executor1, BrowserToolExecutor)


def test_browser_toolset_shared_executor_survives_multiple_subagents():
    """测试 N 个连续的 BrowserToolSet.create() 调用都获得相同的执行器。

    模拟一个父级智能体 + 多个子智能体，每个解析 browser_tool_set。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)

        # 父 + 3 子智能体
        all_tools = [BrowserToolSet.create(conv_state=conv_state) for _ in range(4)]
        executors = [tools[0].executor for tools in all_tools]

        # 全部必须是完全相同的实例
        for executor in executors:
            assert executor is executors[0]


def test_browser_toolset_shared_executor_reset():
    """测试重置 _shared_executor 是否允许创建新的执行程序。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools1 = BrowserToolSet.create(conv_state=conv_state)
        executor1 = tools1[0].executor

        # 重置单例
        BrowserToolSet._shared_executor = None

        tools2 = BrowserToolSet.create(conv_state=conv_state)
        executor2 = tools2[0].executor

        # 重置后，应创建一个新的执行器
        assert executor1 is not executor2


def test_browser_toolset_does_not_hold_shared_lock_while_constructing():
    """回归测试过时的执行器终结器死锁 create()。"""

    def fake_init(self, **_kwargs):
        assert not BrowserToolSet._shared_executor_lock.locked()
        self.full_output_save_dir = None
        self._initialized = False
        self._cleanup_initiated = True
        self._close_lock = threading.Lock()
        self._action_timeout_seconds = 30.0
        self._async_executor = MagicMock()
        self._async_executor.close = MagicMock()

    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        with patch.object(BrowserToolExecutor, "__init__", fake_init):
            tools = BrowserToolSet.create(conv_state=conv_state)

    assert tools[0].executor is BrowserToolSet._shared_executor


def test_browser_toolset_initial_create_serializes_candidate_construction():
    """并发子智能体创建不应替换第一个配置的执行器。"""
    configured_init_started = threading.Event()
    release_configured_init = threading.Event()
    init_configs: list[dict[str, object]] = []
    executors: dict[str, BrowserToolExecutor] = {}
    errors: list[BaseException] = []

    def fake_init(self, **kwargs):
        init_configs.append(kwargs.copy())
        self.full_output_save_dir = kwargs.get("full_output_save_dir")
        self.headless = kwargs.get("headless")
        self.allowed_domains = kwargs.get("allowed_domains")
        self._initialized = False
        self._cleanup_initiated = True
        self._close_lock = threading.Lock()
        self._action_timeout_seconds = 30.0
        self._async_executor = MagicMock()
        self._async_executor.close = MagicMock()

        if kwargs.get("headless") is False:
            configured_init_started.set()
            assert release_configured_init.wait(timeout=2.0)

    def create_tools(
        name: str,
        conv_state: ConversationState,
        **executor_config: object,
    ) -> None:
        try:
            tools = BrowserToolSet.create(conv_state=conv_state, **executor_config)
            executor = tools[0].executor
            assert isinstance(executor, BrowserToolExecutor)
            executors[name] = executor
        except BaseException as error:
            errors.append(error)

    with tempfile.TemporaryDirectory() as temp_dir:
        parent_state = _create_test_conv_state(temp_dir)
        subagent_state = _create_test_conv_state(temp_dir)
        with patch.object(BrowserToolExecutor, "__init__", fake_init):
            parent_thread = threading.Thread(
                target=create_tools,
                args=("parent", parent_state),
                kwargs={"headless": False, "allowed_domains": ["example.com"]},
            )
            parent_thread.start()
            assert configured_init_started.wait(timeout=2.0)

            subagent_thread = threading.Thread(
                target=create_tools,
                args=("subagent", subagent_state),
            )
            subagent_thread.start()

            release_configured_init.set()
            parent_thread.join(timeout=2.0)
            subagent_thread.join(timeout=2.0)

    assert not parent_thread.is_alive()
    assert not subagent_thread.is_alive()
    assert not errors
    assert len(init_configs) == 1
    assert init_configs[0]["headless"] is False
    assert init_configs[0]["allowed_domains"] == ["example.com"]
    assert executors["parent"] is executors["subagent"]
    assert executors["parent"] is BrowserToolSet._shared_executor


def test_browser_toolset_create_waits_for_shared_executor_close():
    """并发 create() 应等待关闭共享执行器清理。"""
    cleanup_started = threading.Event()
    release_cleanup = threading.Event()
    create_finished = threading.Event()
    init_configs: list[dict[str, object]] = []
    executors: dict[str, BrowserToolExecutor] = {}
    errors: list[BaseException] = []

    def fake_init(self, **kwargs):
        init_configs.append(kwargs.copy())
        self.full_output_save_dir = kwargs.get("full_output_save_dir")
        self._config = {}
        self._initialized = False
        self._cleanup_initiated = False
        self._close_lock = threading.Lock()
        self._action_timeout_seconds = 30.0
        self._async_executor = MagicMock()
        self._async_executor.close = MagicMock()

        if len(init_configs) == 1:
            self._async_executor.run_async.side_effect = _block_cleanup

    def _block_cleanup(*_args, **_kwargs):
        cleanup_started.set()
        assert release_cleanup.wait(timeout=2.0)

    def create_tools(conv_state: ConversationState) -> None:
        try:
            tools = BrowserToolSet.create(conv_state=conv_state)
            executor = tools[0].executor
            assert isinstance(executor, BrowserToolExecutor)
            executors["created"] = executor
        except BaseException as error:
            errors.append(error)
        finally:
            create_finished.set()

    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        with patch.object(BrowserToolExecutor, "__init__", fake_init):
            old_executor = BrowserToolSet.create(conv_state=conv_state)[0].executor
            assert isinstance(old_executor, BrowserToolExecutor)

            close_thread = threading.Thread(target=old_executor.close)
            close_thread.start()
            assert cleanup_started.wait(timeout=2.0)

            create_thread = threading.Thread(target=create_tools, args=(conv_state,))
            create_thread.start()
            assert not create_finished.wait(timeout=0.1)
            assert len(init_configs) == 1

            release_cleanup.set()
            close_thread.join(timeout=2.0)
            create_thread.join(timeout=2.0)

    assert not close_thread.is_alive()
    assert not create_thread.is_alive()
    assert not errors
    assert len(init_configs) == 2
    assert executors["created"] is not old_executor
    assert executors["created"] is BrowserToolSet._shared_executor


def test_browser_toolset_warns_when_config_ignored(caplog):
    """
    测试当第二个 create() 传递被忽略的配置时是否记录警告。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)

        # 第一次调用设置共享执行器
        BrowserToolSet.create(conv_state=conv_state)

        # 使用不同配置的第二次调用应该发出警告
        with caplog.at_level(
            "WARNING", logger="openhands.tools.browser_use.definition"
        ):
            BrowserToolSet.create(conv_state=conv_state, headless=False)

        assert any("shared executor already exists" in msg for msg in caplog.messages)


def test_browser_toolset_no_warning_when_no_config(caplog):
    """测试当第二个 create() 没有通过额外配置时不会记录任何警告。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)

        BrowserToolSet.create(conv_state=conv_state)

        with caplog.at_level(
            "WARNING", logger="openhands.tools.browser_use.definition"
        ):
            BrowserToolSet.create(conv_state=conv_state)

        assert not any(
            "shared executor already exists" in msg for msg in caplog.messages
        )


def test_browser_toolset_create_tools_can_generate_mcp_schema():
    """测试 BrowserToolSet.create() 中的工具可以生成 MCP 模式。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = BrowserToolSet.create(conv_state=conv_state)

        for tool in tools:
            mcp_tool = tool.to_mcp_tool()

            # 基本模式验证
            assert "name" in mcp_tool
            assert "description" in mcp_tool
            assert "inputSchema" in mcp_tool
            assert mcp_tool["name"] == tool.name
            assert mcp_tool["description"] == tool.description

            # 模式应具有正确的结构
            input_schema = mcp_tool["inputSchema"]
            assert input_schema["type"] == "object"
            assert "properties" in input_schema


def test_browser_toolset_create_no_parameters():
    """测试 BrowserToolSet.create() 在没有参数的情况下是否可以工作。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        # 不应引发任何异常
        tools = BrowserToolSet.create(conv_state=conv_state)
        assert len(tools) > 0


def test_browser_toolset_inheritance():
    """测试 BrowserToolSet 是否正确继承自 Tool。"""
    assert issubclass(BrowserToolSet, ToolDefinition)

    # BrowserToolSet 不应该直接实例化（它是一个工厂） create 方法返回一个列表，而不是
    # BrowserToolSet 的实例
    #
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = BrowserToolSet.create(conv_state=conv_state)
        for tool in tools:
            assert not isinstance(tool, BrowserToolSet)
            assert isinstance(tool, ToolDefinition)


def test_browser_toolset_create_degrades_when_executor_fails(caplog):
    """无法启动的浏览器不会产生任何浏览器工具，而是会引发。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        with patch.object(
            BrowserToolSet,
            "_get_or_create_shared_executor",
            side_effect=AttributeError("'Server' object has no attribute 'list_tools'"),
        ):
            with caplog.at_level(logging.WARNING):
                tools = BrowserToolSet.create(conv_state=conv_state)

    assert tools == []
    assert "Browser tools are unavailable" in caplog.text


def test_resolve_tool_survives_browser_executor_failure():
    """工具解析不得传播浏览器启动失败。

    每当安装了不兼容的 browser_use/mcp 对时，该异常就会在每个聊天请求中以 500 的形式
    到达智能体服务器。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        with patch.object(
            BrowserToolSet,
            "_get_or_create_shared_executor",
            side_effect=AttributeError("'Server' object has no attribute 'list_tools'"),
        ):
            resolved = resolve_tool(Tool(name=BrowserToolSet.name), conv_state)

    assert list(resolved) == []


def _initial_system_prompt(agent: Agent, temp_dir: str) -> SystemPromptEvent:
    state = ConversationState.create(
        id=uuid4(), agent=agent, workspace=LocalWorkspace(working_dir=temp_dir)
    )
    events: list[Event] = []
    agent.init_state(state, on_event=events.append)
    (event,) = [e for e in events if isinstance(e, SystemPromptEvent)]
    return event


def _agent(
    tools: list[Tool], system_prompt: str | None = None, persona: str | None = None
) -> Agent:
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(
        llm=llm,
        tools=tools,
        system_prompt=system_prompt,
        persona=persona,
        system_prompt_kwargs={"soul_content": "Test soul."},
    )


def test_browser_guidance_renders_once_before_external_services():
    with tempfile.TemporaryDirectory() as temp_dir:
        with_browser = _initial_system_prompt(
            _agent([Tool(name=BrowserToolSet.name)]), temp_dir
        )
        without = _initial_system_prompt(_agent([]), temp_dir)

    assert with_browser.system_prompt.text == without.system_prompt.text.replace(
        "<EXTERNAL_SERVICES>", f"{BROWSER_PROMPT_GUIDANCE}\n\n<EXTERNAL_SERVICES>"
    )
    tool_schemas = json.dumps([t.to_openai_tool() for t in with_browser.tools])
    assert "<BROWSER_TOOLS>" not in tool_schemas


def test_custom_system_prompt_keeps_browser_guidance():
    with tempfile.TemporaryDirectory() as temp_dir:
        event = _initial_system_prompt(
            _agent([Tool(name=BrowserToolSet.name)], "CUSTOM SYSTEM PROMPT"), temp_dir
        )

    assert event.system_prompt.text == (
        f"CUSTOM SYSTEM PROMPT\n\n{BROWSER_PROMPT_GUIDANCE}"
    )


def test_persona_keeps_browser_guidance():
    with tempfile.TemporaryDirectory() as temp_dir:
        event = _initial_system_prompt(
            _agent([Tool(name=BrowserToolSet.name)], persona="You are a chef."),
            temp_dir,
        )

    assert event.system_prompt.text.startswith("You are a chef.")
    assert BROWSER_PROMPT_GUIDANCE in event.system_prompt.text


def test_no_browser_guidance_when_browser_fails_to_start():
    with (
        tempfile.TemporaryDirectory() as temp_dir,
        patch.object(
            BrowserToolSet,
            "_get_or_create_shared_executor",
            side_effect=RuntimeError("chromium failed to start"),
        ),
    ):
        event = _initial_system_prompt(
            _agent([Tool(name=BrowserToolSet.name)]), temp_dir
        )

    assert not any(t.name.startswith("browser_") for t in event.tools)
    assert "<BROWSER_TOOLS>" not in event.system_prompt.text


def test_migrated_profile_with_pinned_browser_resolves_on_browserless_runtime():
    """已迁移的配置文件固定 `browser_tool_set` 无需浏览器即可解析。"""
    from openhands.sdk.tool.defaults import (
        fold_retired_tool_switches,
        resolve_tool_specs,
    )
    from openhands.sdk.tool.registry import resolve_tool

    migrated = fold_retired_tool_switches({"tools": None, "enable_sub_agents": True})[
        "tools"
    ]
    specs = resolve_tool_specs(migrated)
    assert [spec.name for spec in specs] == [
        "terminal",
        "file_editor",
        "task_tracker",
        "browser_tool_set",
        "task_tool_set",
        "switch_llm",
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        with patch.object(
            BrowserToolSet,
            "_get_or_create_shared_executor",
            side_effect=RuntimeError("no chromium on this host"),
        ):
            browser_spec = next(s for s in specs if s.name == "browser_tool_set")
            resolved = resolve_tool(browser_spec, conv_state)

    assert list(resolved) == []
