"""测试委托工具。"""

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from openhands.sdk.agent.utils import fix_malformed_tool_arguments
from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.hooks.config import HookConfig, HookDefinition, HookMatcher
from openhands.sdk.llm import LLM, TextContent
from openhands.sdk.llm.call_context import LLMCallContext
from openhands.sdk.subagent.registry import (
    _reset_registry_for_tests,
    register_agent,
)
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.tools.delegate import (
    DelegateExecutor,
    DelegateObservation,
)
from openhands.tools.delegate.definition import DelegateAction
from openhands.tools.preset import register_builtins_agents


def create_test_executor_and_parent():
    """创建测试执行器和父级对话的帮助程序。"""
    llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        base_url="https://api.openai.com/v1",
    )

    parent_conversation = MagicMock()
    parent_conversation.id = uuid.uuid4()
    parent_conversation.agent.llm = llm
    parent_conversation.agent.cli_mode = True
    parent_conversation.state.workspace.working_dir = "/tmp"
    parent_conversation.state.persistence_dir = None
    parent_conversation.visualize = False
    parent_conversation.get_llm_call_context.return_value = LLMCallContext(
        prompt_cache_key=str(parent_conversation.id),
        session_id=str(parent_conversation.id),
    )

    executor = DelegateExecutor()

    return executor, parent_conversation


def create_mock_conversation():
    """创建模拟对象对话的帮助程序。"""
    mock_conv = MagicMock()
    mock_conv.id = str(uuid.uuid4())
    mock_conv.state.execution_status = ConversationExecutionStatus.FINISHED
    return mock_conv


def test_delegate_action_creation():
    """测试创建 DelegateAction 个实例。"""
    # 测试生成动作
    spawn_action = DelegateAction(command="spawn", ids=["agent1", "agent2"])
    assert spawn_action.command == "spawn"
    assert spawn_action.ids == ["agent1", "agent2"]
    assert spawn_action.tasks is None

    # 测试委托操作
    delegate_action = DelegateAction(
        command="delegate",
        tasks={"agent1": "Analyze code quality", "agent2": "Write tests"},
    )
    assert delegate_action.command == "delegate"
    assert delegate_action.tasks == {
        "agent1": "Analyze code quality",
        "agent2": "Write tests",
    }
    assert delegate_action.ids is None


def test_delegate_observation_creation():
    """测试创建 DelegateObservation 个实例。"""
    # 使用字符串输出测试spawn 观测结果
    spawn_observation = DelegateObservation.from_text(
        text="spawn: Sub-agents created successfully",
        command="spawn",
    )
    assert isinstance(spawn_observation.content, list)
    assert spawn_observation.text == "spawn: Sub-agents created successfully"
    # 验证 to_llm_content 返回 TextContent
    llm_content = spawn_observation.to_llm_content
    assert len(llm_content) == 1
    assert isinstance(llm_content[0], TextContent)
    assert llm_content[0].text == "spawn: Sub-agents created successfully"

    # 带有字符串输出的测试委托观测结果
    delegate_observation = DelegateObservation.from_text(
        text=(
            "delegate: Tasks completed successfully\n\nResults:\n"
            "1. Result 1\n2. Result 2"
        ),
        command="delegate",
    )
    assert isinstance(delegate_observation.content, list)
    assert "Tasks completed successfully" in delegate_observation.text
    assert "Result 1" in delegate_observation.text
    assert "Result 2" in delegate_observation.text
    # 验证 to_llm_content
    llm_content = delegate_observation.to_llm_content
    assert len(llm_content) == 1
    assert isinstance(llm_content[0], TextContent)
    assert "Tasks completed successfully" in llm_content[0].text


def test_delegate_executor_delegate():
    """测试DelegateExecutor委托操作。"""
    executor, parent_conversation = create_test_executor_and_parent()
    register_builtins_agents()
    # 首先产生一些智能体
    spawn_action = DelegateAction(command="spawn", ids=["agent1", "agent2"])
    spawn_observation = executor(spawn_action, parent_conversation)
    assert isinstance(spawn_observation.content, list)
    assert "Successfully spawned" in spawn_observation.text

    # 然后将任务委派给他们
    delegate_action = DelegateAction(
        command="delegate",
        tasks={"agent1": "Analyze code quality", "agent2": "Write tests"},
    )

    with patch.object(executor, "_delegate_tasks") as mock_delegate:
        mock_observation = DelegateObservation.from_text(
            text=(
                "delegate: Tasks completed successfully\n\nResults:\n"
                "1. Agent agent1: Code analysis complete\n"
                "2. Agent agent2: Tests written"
            ),
            command="delegate",
        )
        mock_delegate.return_value = mock_observation

        observation = executor(delegate_action, parent_conversation)

    assert isinstance(observation, DelegateObservation)
    assert isinstance(observation.content, list)
    text_content = observation.text
    assert "Agent agent1: Code analysis complete" in text_content
    assert "Agent agent2: Tests written" in text_content


def test_delegate_executor_missing_task():
    """使用空任务字典测试 DelegateExecutor 委托。"""
    executor, parent_conversation = create_test_executor_and_parent()

    # 在没有任务的情况下测试委托操作
    action = DelegateAction(command="delegate", tasks={})

    observation = executor(action, parent_conversation)

    assert isinstance(observation, DelegateObservation)
    # 错误消息应该在错误字段中
    assert observation.is_error
    assert observation.is_error is True
    content_text = observation.text
    assert (
        "task is required" in content_text.lower()
        or "at least one task" in content_text.lower()
    )


def test_delegation_manager_init():
    """测试DelegateExecutor初始化。"""
    mock_conv = create_mock_conversation()
    manager = DelegateExecutor()

    manager._parent_conversation = mock_conv

    # 测试我们是否可以访问父级对话
    assert manager.parent_conversation == mock_conv
    assert str(manager.parent_conversation.id) == str(mock_conv.id)

    # 测试子智能体 dict 最初是否为空
    assert len(manager._sub_agents) == 0


def test_close_closes_spawned_sub_agents():
    """关闭委托执行器会释放生成的子对话。"""
    register_builtins_agents()
    executor, parent_conversation = create_test_executor_and_parent()
    parent_conversation._visualizer = None

    observation = executor(
        DelegateAction(command="spawn", ids=["sub1"]), parent_conversation
    )

    assert "Successfully spawned" in observation.text
    sub_conversation = executor._sub_agents["sub1"]
    assert sub_conversation._cleanup_initiated is False

    executor.close()

    assert sub_conversation._cleanup_initiated is True
    assert executor._sub_agents == {}


def test_spawn_closes_replaced_sub_agent():
    """重新生成 ID 会关闭它所替换的对话。"""
    register_builtins_agents()
    executor, parent_conversation = create_test_executor_and_parent()
    parent_conversation._visualizer = None

    executor(DelegateAction(command="spawn", ids=["sub1"]), parent_conversation)
    first_conversation = executor._sub_agents["sub1"]

    observation = executor(
        DelegateAction(command="spawn", ids=["sub1"]), parent_conversation
    )

    replacement_conversation = executor._sub_agents["sub1"]
    assert "Successfully spawned" in observation.text
    assert replacement_conversation is not first_conversation
    assert first_conversation._cleanup_initiated is True
    assert replacement_conversation._cleanup_initiated is False

    executor.close()


def test_spawn_rolls_back_partial_batch_when_agent_type_missing():
    """失败的生成批次不会留下创建的子对话。"""
    register_builtins_agents()
    executor, parent_conversation = create_test_executor_and_parent()
    parent_conversation._visualizer = None

    observation = executor(
        DelegateAction(
            command="spawn",
            ids=["sub1", "missing"],
            agent_types=["default", "does-not-exist"],
        ),
        parent_conversation,
    )

    assert observation.is_error is True
    assert executor._sub_agents == {}


def test_spawn_disables_streaming_for_sub_agents():
    """测试生成的子智能体已禁用流式传输。

    当父对话启用了流式传输但子智能体没有 token 回调时，这可以防止出现“流式传输需要
    on_token 回调”错误。
    """
    # 创建启用流式传输的父级 LLM
    parent_llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        base_url="https://api.openai.com/v1",
        stream=True,  # 父级已启用流式传输
    )
    register_builtins_agents()

    parent_conversation = MagicMock()
    parent_conversation.id = uuid.uuid4()
    parent_conversation.agent.llm = parent_llm
    parent_conversation.agent.cli_mode = True
    parent_conversation.state.workspace.working_dir = "/tmp"
    parent_conversation.state.persistence_dir = None
    parent_conversation._visualizer = None

    executor = DelegateExecutor()

    # 生成智能体
    spawn_action = DelegateAction(command="spawn", ids=["test_agent"])
    observation = executor(spawn_action, parent_conversation)

    # 验证生成成功
    assert "Successfully spawned" in observation.text
    assert "test_agent" in executor._sub_agents

    # 验证子智能体的 LLM 已禁用流式传输
    sub_conversation = executor._sub_agents["test_agent"]
    sub_llm = sub_conversation.agent.llm
    assert sub_llm.stream is False, "Sub-agent LLM should have streaming disabled"

    # 验证父级 LLM 仍启用流式传输（未发生突变）
    assert parent_llm.stream is True, "Parent LLM should still have streaming enabled"


def test_spawn_gives_sub_agents_independent_metrics():
    """子智能体不得共享父级的 Metrics 对象。"""
    register_builtins_agents()
    parent_llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        base_url="https://api.openai.com/v1",
    )

    parent_conversation = MagicMock()
    parent_conversation.id = uuid.uuid4()
    parent_conversation.agent.llm = parent_llm
    parent_conversation.state.workspace.working_dir = "/tmp"
    parent_conversation.state.persistence_dir = None
    parent_conversation._visualizer = None

    executor = DelegateExecutor()
    spawn_action = DelegateAction(command="spawn", ids=["a1", "a2"])
    executor(spawn_action, parent_conversation)

    a1_llm = executor._sub_agents["a1"].agent.llm
    a2_llm = executor._sub_agents["a2"].agent.llm

    # 每个子智能体必须有自己的指标，而不是父级的指标
    assert a1_llm.metrics is not parent_llm.metrics
    assert a2_llm.metrics is not parent_llm.metrics
    assert a1_llm.metrics is not a2_llm.metrics

    # 改变子智能体的指标不得影响父级
    before = parent_llm.metrics.accumulated_cost
    a1_llm.metrics.add_cost(1.00)
    assert parent_llm.metrics.accumulated_cost == before
    a2_llm.metrics.add_cost(1.00)
    assert parent_llm.metrics.accumulated_cost == before


def test_delegate_merges_metrics_into_parent():
    """委派后，子智能体指标将出现在父级统计信息中。"""
    register_builtins_agents()
    parent_llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        base_url="https://api.openai.com/v1",
    )
    parent_stats = ConversationStats()
    parent_stats.usage_to_metrics["agent"] = parent_llm.metrics

    parent_conversation = MagicMock()
    parent_conversation.id = uuid.uuid4()
    parent_conversation.agent.llm = parent_llm
    parent_conversation.state.workspace.working_dir = "/tmp"
    parent_conversation.state.persistence_dir = None
    parent_conversation._visualizer = None
    parent_conversation.conversation_stats = parent_stats

    executor = DelegateExecutor()
    spawn_action = DelegateAction(command="spawn", ids=["a1", "a2"])
    executor(spawn_action, parent_conversation)

    # 将 LLMs 连接到子转化统计数据（模拟 _ensure_agent_ready 的作用）
    for agent_id in ("a1", "a2"):
        sub_conv = executor._sub_agents[agent_id]
        llm = sub_conv.agent.llm
        sub_conv.conversation_stats.usage_to_metrics[llm.usage_id] = llm.metrics

    # 模拟子智能体 LLM 使用情况
    a1_llm = executor._sub_agents["a1"].agent.llm
    a2_llm = executor._sub_agents["a2"].agent.llm
    a1_llm.metrics.add_cost(1.00)
    a1_llm.metrics.add_token_usage(
        prompt_tokens=100,
        completion_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=128000,
        response_id="a1_r1",
    )
    a2_llm.metrics.add_cost(2.00)
    a2_llm.metrics.add_token_usage(
        prompt_tokens=200,
        completion_tokens=100,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=128000,
        response_id="a2_r1",
    )

    # 运行委托（修补 send_message/运行，因此不会发生真正的 LLM 调用）
    with (
        patch.object(executor._sub_agents["a1"], "send_message"),
        patch.object(executor._sub_agents["a1"], "run"),
        patch.object(executor._sub_agents["a2"], "send_message"),
        patch.object(executor._sub_agents["a2"], "run"),
    ):
        delegate_action = DelegateAction(
            command="delegate",
            tasks={"a1": "task 1", "a2": "task 2"},
        )
        executor(delegate_action, parent_conversation)

    # 子智能体指标现在位于委托下的父统计信息中：键
    assert "delegate:a1" in parent_stats.usage_to_metrics
    assert "delegate:a2" in parent_stats.usage_to_metrics
    assert parent_stats.usage_to_metrics["delegate:a1"].accumulated_cost == 1.00
    assert parent_stats.usage_to_metrics["delegate:a2"].accumulated_cost == 2.00

    # 合计包括父项 + 两者子智能体
    combined = parent_stats.get_combined_metrics()
    assert combined.accumulated_cost == 3.00
    accumulated_token_usage = combined.accumulated_token_usage
    assert accumulated_token_usage is not None
    assert accumulated_token_usage.prompt_tokens == 300
    assert accumulated_token_usage.completion_tokens == 150


def test_repeated_delegation_does_not_double_count():
    """两次委托相同的智能体不得重复指标。"""
    register_builtins_agents()
    parent_llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        base_url="https://api.openai.com/v1",
    )
    parent_stats = ConversationStats()
    parent_stats.usage_to_metrics["agent"] = parent_llm.metrics

    parent_conversation = MagicMock()
    parent_conversation.id = uuid.uuid4()
    parent_conversation.agent.llm = parent_llm
    parent_conversation.state.workspace.working_dir = "/tmp"
    parent_conversation.state.persistence_dir = None
    parent_conversation._visualizer = None
    parent_conversation.conversation_stats = parent_stats

    executor = DelegateExecutor()
    spawn_action = DelegateAction(command="spawn", ids=["a1"])
    executor(spawn_action, parent_conversation)

    sub_conv = executor._sub_agents["a1"]
    sub_conv.conversation_stats.usage_to_metrics[sub_conv.agent.llm.usage_id] = (
        sub_conv.agent.llm.metrics
    )

    a1_llm = executor._sub_agents["a1"].agent.llm

    # 第一个授权：子智能体累积 1.00 美元
    a1_llm.metrics.add_cost(1.00)
    with (
        patch.object(executor._sub_agents["a1"], "send_message"),
        patch.object(executor._sub_agents["a1"], "run"),
    ):
        executor(
            DelegateAction(command="delegate", tasks={"a1": "first task"}),
            parent_conversation,
        )
    assert parent_stats.usage_to_metrics["delegate:a1"].accumulated_cost == 1.00

    # 第二次授权：子智能体又累积 2.00 美元（累计 3.00 美元）
    a1_llm.metrics.add_cost(2.00)
    with (
        patch.object(executor._sub_agents["a1"], "send_message"),
        patch.object(executor._sub_agents["a1"], "run"),
    ):
        executor(
            DelegateAction(command="delegate", tasks={"a1": "second task"}),
            parent_conversation,
        )

    # 必须为 3.00 美元（累计），而不是 4.00 美元（重复计算）
    assert parent_stats.usage_to_metrics["delegate:a1"].accumulated_cost == 3.00


def test_issue_2216():
    """重现问题 #2216：DelegateAction 拒绝作为 JSON 字符串发送的任务。

    当 LLM 将 `tasks` 字典序列化为 JSON *string* （而不是 JSON 对象）时，该字符串内的
    值可能包含换行符。 在工具调用参数的外部
    `json.loads` 之后，`\\n` 转义符变成真正的换行符，这使得内部字符串无效 JSON。
    `fix_malformed_tool_arguments` 默默地无法解析它，并将原始字符串传递给
    `DelegateAction.model_validate`
    ，然后引发一个
    `ValidationError`.

    Ref: https://github.com/OpenHands/software-agent-sdk/issues/2216
    """
    # JSON 以 LLM 发出的原始形式呈现 —— 任务是一个 * 字符串*，而不是一个对象，任务描述包
    # 含一个 ``\n``（有效的 JSON 换行符）。
    #
    raw_llm_args = (
        '{"command": "delegate",'
        ' "tasks": "{\\"batch1\\": \\"Build TWO apps\\nFollow instructions\\"}"}'
    )

    # 外部解析成功 - 任务现在是带有真正换行符的 Python str。
    arguments = json.loads(raw_llm_args)
    assert isinstance(arguments["tasks"], str)
    assert "\n" in arguments["tasks"]

    # fix_malformed_tool_arguments 应该将其转换为字典，以便 model_validate 接受它。
    #
    fixed = fix_malformed_tool_arguments(arguments, DelegateAction)
    action = DelegateAction.model_validate(fixed)
    assert isinstance(action.tasks, dict)
    assert action.tasks == {"batch1": "Build TWO apps\nFollow instructions"}


def test_spawn_passes_hook_config_to_sub_conversation():
    """生成的子智能体对话从智能体工厂接收 hook_config。"""
    _reset_registry_for_tests()

    hook_config = HookConfig(
        pre_tool_use=[
            HookMatcher(
                matcher="terminal",
                hooks=[HookDefinition(command="./validate.sh", timeout=10)],
            )
        ]
    )

    agent_def = AgentDefinition(
        name="hooked-agent",
        description="Agent with hooks",
        model="inherit",
        tools=[],
        system_prompt="You are a hooked agent.",
        hooks=hook_config,
    )

    from openhands.sdk.subagent.registry import (
        agent_definition_to_factory,
    )

    factory_func = agent_definition_to_factory(agent_def)
    register_agent(
        name="hooked-agent",
        factory_func=factory_func,
        description=agent_def,
    )

    parent_llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        base_url="https://api.openai.com/v1",
    )

    parent_conversation = MagicMock()
    parent_conversation.id = uuid.uuid4()
    parent_conversation.agent.llm = parent_llm
    parent_conversation.state.workspace.working_dir = "/tmp"
    parent_conversation.state.persistence_dir = None
    parent_conversation._visualizer = None

    executor = DelegateExecutor()
    spawn_action = DelegateAction(
        command="spawn", ids=["h1"], agent_types=["hooked-agent"]
    )
    observation = executor(spawn_action, parent_conversation)

    assert "Successfully spawned" in observation.text
    sub_conv = executor._sub_agents["h1"]
    # 子对话应设置 hook_config
    assert sub_conv._pending_hook_config is not None
    assert len(sub_conv._pending_hook_config.pre_tool_use) == 1
    assert sub_conv._pending_hook_config.pre_tool_use[0].matcher == "terminal"

    _reset_registry_for_tests()


def test_spawn_inherits_persistence_dir_from_parent():
    """
    当父对话持续存在时，子智能体持久化在 subagents/ 子目录下。
    """
    register_builtins_agents()
    parent_llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        base_url="https://api.openai.com/v1",
    )

    parent_conversation = MagicMock()
    parent_conversation.id = uuid.uuid4()
    parent_conversation.agent.llm = parent_llm
    parent_conversation.state.workspace.working_dir = "/tmp"
    parent_conversation.state.persistence_dir = "/tmp/conversations/abc123"
    parent_conversation._visualizer = None

    executor = DelegateExecutor()
    spawn_action = DelegateAction(command="spawn", ids=["sub1"])
    observation = executor(spawn_action, parent_conversation)

    assert "Successfully spawned" in observation.text
    sub_conv = executor._sub_agents["sub1"]
    # 子对话应该在父对话的 persistence_dir + "子智能体" 下有一个 persistence_dir
    #
    sub_persistence_dir = sub_conv._state.persistence_dir
    assert sub_persistence_dir is not None
    assert Path(sub_persistence_dir).exists()
    assert Path(sub_persistence_dir).parent == (
        Path(parent_conversation.state.persistence_dir) / "subagents"
    )


def test_spawn_no_persistence_when_parent_has_none():
    """当父级不持久化时，子智能体也不持久化。"""
    register_builtins_agents()
    parent_llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        base_url="https://api.openai.com/v1",
    )

    parent_conversation = MagicMock()
    parent_conversation.id = uuid.uuid4()
    parent_conversation.agent.llm = parent_llm
    parent_conversation.state.workspace.working_dir = "/tmp"
    parent_conversation.state.persistence_dir = None
    parent_conversation._visualizer = None

    executor = DelegateExecutor()
    spawn_action = DelegateAction(command="spawn", ids=["sub1"])
    observation = executor(spawn_action, parent_conversation)

    assert "Successfully spawned" in observation.text
    sub_conv = executor._sub_agents["sub1"]
    # 子对话不应有 persistence_dir
    assert sub_conv._state.persistence_dir is None
