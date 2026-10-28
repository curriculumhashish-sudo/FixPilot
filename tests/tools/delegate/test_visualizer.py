"""DelegationVisualizer 类的测试。"""

import json
from unittest.mock import MagicMock

from rich.rule import Rule

from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.event import ActionEvent, MessageEvent, ObservationEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.llm.utils.metrics import Metrics
from openhands.sdk.tool import Action, Observation
from openhands.tools.delegate import DelegationVisualizer


class MockDelegateAction(Action):
    """模拟对象测试操作。"""

    command: str = "test command"


class MockDelegateObservation(Observation):
    """模拟对象观测结果用于测试。"""

    result: str = "test result"


def create_tool_call(
    call_id: str, function_name: str, arguments: dict
) -> MessageToolCall:
    """创建 MessageToolCall 的帮助程序。"""
    return MessageToolCall(
        id=call_id,
        name=function_name,
        arguments=json.dumps(arguments),
        origin="completion",
    )


def test_delegation_visualizer_user_message_without_sender():
    """没有发件人的测试用户消息显示“用户消息至 [智能体] 智能体”。"""
    visualizer = DelegationVisualizer(name="MainAgent")
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()
    mock_state.events = []
    visualizer.initialize(mock_state)

    user_message = Message(role="user", content=[TextContent(text="Hello")])
    user_event = MessageEvent(source="user", llm_message=user_message)
    block = visualizer._create_message_event_block(user_event)

    assert block is not None
    # 该块包含规则作为带有标题的第一个元素
    assert "User Message to Main Agent Agent" in str(block.renderables[0])


def test_delegation_visualizer_user_message_with_sender():
    """测试委托消息显示发送者和接收者智能体名称。"""  # noqa: E501
    visualizer = DelegationVisualizer(name="Lodging Expert")
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()
    mock_state.events = []
    visualizer.initialize(mock_state)

    delegated_message = Message(
        role="user", content=[TextContent(text="Task from parent")]
    )
    delegated_event = MessageEvent(
        source="user", llm_message=delegated_message, sender="Delegator"
    )
    block = visualizer._create_message_event_block(delegated_event)

    assert block is not None
    # 该块包含规则作为带有标题的第一个元素
    assert "Delegator Agent Message to Lodging Expert Agent" in str(
        block.renderables[0]
    )


def test_delegation_visualizer_framework_user_role_messages_use_event_source():
    """框架消息保留用户 LLM 角色，而不是由人类编写的。"""
    visualizer = DelegationVisualizer(name="WorkerAgent")
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()
    mock_state.events = []
    visualizer.initialize(mock_state)

    environment_event = MessageEvent(
        source="environment",
        llm_message=Message(
            role="user",
            content=[TextContent(text="Correct the missing tool call.")],
        ),
    )
    hook_event = MessageEvent(
        source="hook",
        llm_message=Message(
            role="user",
            content=[TextContent(text="Apply hook feedback.")],
        ),
    )

    environment_block = visualizer._create_event_block(environment_event)
    hook_block = visualizer._create_event_block(hook_event)

    assert environment_block is not None
    assert hook_block is not None
    environment_header = environment_block.renderables[0]
    hook_header = hook_block.renderables[0]
    assert isinstance(environment_header, Rule)
    assert isinstance(hook_header, Rule)
    assert "Message from Environment to Worker Agent Agent" in str(environment_header)
    assert "Message from Hook to Worker Agent Agent" in str(hook_header)
    assert "User Message" not in str(environment_header)
    assert "User Message" not in str(hook_header)
    assert environment_header.style == "magenta"
    assert hook_header.style == "magenta"


def test_delegation_visualizer_skip_user_messages_uses_event_source():
    """跳过人工输入必须保留具有用户 LLM 角色的框架反馈。"""
    visualizer = DelegationVisualizer(name="WorkerAgent", skip_user_messages=True)
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()
    mock_state.events = []
    visualizer.initialize(mock_state)

    human_event = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Human input")]),
    )
    environment_event = MessageEvent(
        source="environment",
        llm_message=Message(
            role="user",
            content=[TextContent(text="Framework feedback")],
        ),
    )

    assert visualizer._create_event_block(human_event) is None
    assert visualizer._create_event_block(environment_event) is not None


def test_delegation_visualizer_agent_response_to_user():
    """对用户的测试智能体响应显示“消息从 [智能体] 智能体发送给用户”。"""
    visualizer = DelegationVisualizer(name="MainAgent")
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()
    mock_state.events = []
    visualizer.initialize(mock_state)

    agent_message = Message(
        role="assistant", content=[TextContent(text="Response to user")]
    )
    response_event = MessageEvent(source="agent", llm_message=agent_message)
    block = visualizer._create_message_event_block(response_event)

    assert block is not None
    # 该块包含规则作为带有标题的第一个元素
    assert "Message from Main Agent Agent to User" in str(block.renderables[0])


def test_delegation_visualizer_agent_response_to_delegator():
    """框架反馈不得隐藏父级智能体接收者。"""
    visualizer = DelegationVisualizer(name="Lodging Expert")
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()

    # 使用委托消息设置事件历史记录
    delegated_message = Message(
        role="user", content=[TextContent(text="Task from parent")]
    )
    delegated_event = MessageEvent(
        source="user", llm_message=delegated_message, sender="Delegator"
    )
    corrective_nudge = MessageEvent(
        source="environment",
        llm_message=Message(
            role="user",
            content=[TextContent(text="Correct the missing tool call.")],
        ),
    )
    mock_state.events = [delegated_event, corrective_nudge]
    visualizer.initialize(mock_state)

    # 子智能体回复
    agent_message = Message(
        role="assistant", content=[TextContent(text="Response to delegator")]
    )
    response_event = MessageEvent(source="agent", llm_message=agent_message)
    block = visualizer._create_message_event_block(response_event)

    assert block is not None
    # 该块包含规则作为带有标题的第一个元素
    assert "Lodging Expert Agent Message to Delegator Agent" in str(
        block.renderables[0]
    )


def test_delegation_visualizer_formats_agent_names():
    """测试智能体名称格式正确（snake_case 为标题大小写）。"""
    visualizer = DelegationVisualizer(name="lodging_expert")
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()

    # 使用来自另一个智能体的委托消息设置事件历史记录
    delegated_message = Message(
        role="user", content=[TextContent(text="Task from parent")]
    )
    delegated_event = MessageEvent(
        source="user", llm_message=delegated_message, sender="main_delegator"
    )
    mock_state.events = [delegated_event]
    visualizer.initialize(mock_state)

    # 为委托消息创建块
    block = visualizer._create_message_event_block(delegated_event)
    assert block is not None
    # 该块包含规则作为带有标题的第一个元素
    assert "Main Delegator Agent Message to Lodging Expert Agent" in str(
        block.renderables[0]
    )

    # 子智能体回复
    agent_message = Message(
        role="assistant", content=[TextContent(text="Response to delegator")]
    )
    response_event = MessageEvent(source="agent", llm_message=agent_message)
    block = visualizer._create_message_event_block(response_event)

    assert block is not None
    # 该块包含规则作为带有标题的第一个元素
    assert "Lodging Expert Agent Message to Main Delegator Agent" in str(
        block.renderables[0]
    )


def test_delegation_visualizer_action_event():
    """测试操作事件在标题中显示智能体名称。"""
    visualizer = DelegationVisualizer(name="lodging_expert")
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()
    mock_state.events = []
    visualizer.initialize(mock_state)

    # 创建适当的操作事件
    action = MockDelegateAction(command="search hotels")
    tool_call = create_tool_call("call_123", "search", {"command": "search hotels"})
    action_event = ActionEvent(
        thought=[TextContent(text="Searching for hotels")],
        action=action,
        tool_name="search",
        tool_call_id="call_123",
        tool_call=tool_call,
        llm_response_id="response_456",
    )

    block = visualizer._create_event_block(action_event)

    assert block is not None
    # 该块包含规则作为带有标题的第一个元素
    assert "Lodging Expert Agent Action" in str(block.renderables[0])


def test_delegation_visualizer_action_event_shows_per_request_usage():
    """Regression: DelegationVisualizer 覆盖 _create_event_block 并且必须
    将事件转发到 _format_metrics_subtitle。 缺少它，ActionEvent 字幕会无声地只显示累
    计数，而上下文压缩（由父类处理，唯一其他事件类
    型携带llm_response_id）则按请求显示，混合格式在一个代理转录中（#4105）。
    """
    stats = ConversationStats()
    metrics = Metrics(model_name="test-model")
    metrics.add_token_usage(
        prompt_tokens=1000,
        completion_tokens=100,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="response_1",
    )
    metrics.add_token_usage(
        prompt_tokens=2000,
        completion_tokens=200,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="response_2",
    )
    stats.usage_to_metrics["agent"] = metrics

    visualizer = DelegationVisualizer(name="lodging_expert")
    mock_state = MagicMock()
    mock_state.stats = stats
    mock_state.events = []
    visualizer.initialize(mock_state)

    action = MockDelegateAction(command="search hotels")
    tool_call = create_tool_call("call_123", "search", {"command": "search hotels"})
    action_event = ActionEvent(
        thought=[TextContent(text="Searching for hotels")],
        action=action,
        tool_name="search",
        tool_call_id="call_123",
        tool_call=tool_call,
        llm_response_id="response_2",
    )

    block = visualizer._create_event_block(action_event)

    assert block is not None
    rendered = "".join(str(r) for r in block.renderables)
    # response_2 的每个请求使用情况，而不仅仅是运行累积总数。
    assert "input 2K (total 3K)" in rendered
    assert "output 200 (total 300)" in rendered


def test_delegation_visualizer_observation_event():
    """测试观测结果事件在标题中显示智能体名称。"""
    visualizer = DelegationVisualizer(name="main_delegator")
    mock_state = MagicMock()
    mock_state.stats = ConversationStats()
    mock_state.events = []
    visualizer.initialize(mock_state)

    # 创建适当的观测结果事件
    observation = MockDelegateObservation(result="Hotel search results")
    observation_event = ObservationEvent(
        source="environment",
        observation=observation,
        tool_name="search",
        tool_call_id="call_123",
        action_id="action_789",
    )

    block = visualizer._create_event_block(observation_event)

    assert block is not None
    # 该块包含规则作为带有标题的第一个元素
    assert "Main Delegator Agent Observation" in str(block.renderables[0])


def test_delegation_visualizer_create_sub_visualizer():
    """测试 create_sub_visualizer 为子智能体创建一个新的可视化工具。"""
    parent_visualizer = DelegationVisualizer(
        name="main_delegator",
        highlight_regex={"test": "bold"},
        skip_user_messages=True,
    )

    # 为子智能体创建子可视化工具
    sub_visualizer = parent_visualizer.create_sub_visualizer("lodging_expert")

    # 验证子可视化器是 DelegationVisualizer
    assert isinstance(sub_visualizer, DelegationVisualizer)
    # 验证子可视化器具有正确的智能体名称
    assert sub_visualizer._name == "lodging_expert"
    # 验证设置是从父级继承的
    assert sub_visualizer._highlight_patterns == {"test": "bold"}
    assert sub_visualizer._skip_user_messages is True


def test_delegation_visualizer_create_sub_visualizer_with_defaults():
    """测试 create_sub_visualizer 适用于默认父级设置。"""
    parent_visualizer = DelegationVisualizer(name="parent")

    sub_visualizer = parent_visualizer.create_sub_visualizer("child_agent")

    assert isinstance(sub_visualizer, DelegationVisualizer)
    assert sub_visualizer._name == "child_agent"
    # 默认值应该被继承
    assert sub_visualizer._highlight_patterns is not None  # 有默认模式
    assert sub_visualizer._skip_user_messages is False


def test_delegation_visualizer_user_message_labels_totals():
    """用户MessageEvents不携带llm_response_id，因此委托消息
    块只能显示运行总计 - 它们必须标记为“（总计）”，而不是在每个请求的字幕旁边打印为裸
    数字（#4105）。
    """
    stats = ConversationStats()
    metrics = Metrics(model_name="test-model")
    metrics.add_token_usage(
        prompt_tokens=1000,
        completion_tokens=100,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="response_1",
    )
    stats.usage_to_metrics["agent"] = metrics

    visualizer = DelegationVisualizer(name="MainAgent")
    mock_state = MagicMock()
    mock_state.stats = stats
    mock_state.events = []
    visualizer.initialize(mock_state)

    user_message = Message(role="user", content=[TextContent(text="Hello")])
    user_event = MessageEvent(source="user", llm_message=user_message)
    block = visualizer._create_message_event_block(user_event)

    assert block is not None
    rendered = "".join(str(r) for r in block.renderables)
    assert "input (total 1K)" in rendered
    assert "output (total 100)" in rendered
    assert "$ (total 0.00)" in rendered


def _delegate_batch_action(call_id: str, response_id: str) -> ActionEvent:
    """为委托并行批量测试构建 ActionEvent。"""
    return ActionEvent(
        thought=[TextContent(text="Searching")],
        action=MockDelegateAction(command="search"),
        tool_name="search",
        tool_call_id=call_id,
        tool_call=create_tool_call(call_id, "search", {}),
        llm_response_id=response_id,
    )


def test_delegation_visualizer_parallel_batch_siblings_fall_back():
    """代表成绩单中的并行工具调用：仅第一个 ActionEvent
    共享llm_response_id批次的数量显示每个请求的数量； siblings显示总计，以避免在每个
    事件下重复使用(#4189)。
    """
    stats = ConversationStats()
    metrics = Metrics(model_name="test-model")
    # 之前的请求，因此运行总数 (3K/300) 与该批次的每个请求使用情况 (2K/200) 不同。
    #
    metrics.add_token_usage(
        prompt_tokens=1000,
        completion_tokens=100,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="resp_prev",
    )
    metrics.add_token_usage(
        prompt_tokens=2000,
        completion_tokens=200,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="resp_batch",
    )
    stats.usage_to_metrics["agent"] = metrics

    a1 = _delegate_batch_action("call_1", "resp_batch")
    a2 = _delegate_batch_action("call_2", "resp_batch")

    visualizer = DelegationVisualizer(name="lodging_expert")
    mock_state = MagicMock()
    mock_state.stats = stats
    visualizer.initialize(mock_state)

    # 按流顺序渲染：a1 是批处理主批，a2 是同级批处理。
    primary_block = visualizer._create_event_block(a1)
    sibling_block = visualizer._create_event_block(a2)
    assert primary_block is not None and sibling_block is not None
    primary = "".join(str(r) for r in primary_block.renderables)
    sibling = "".join(str(r) for r in sibling_block.renderables)

    # 主要显示每个请求的使用情况； 兄弟姐妹仅显示总计。
    assert "input 2K (total 3K)" in primary
    assert "input (total 3K)" in sibling
    assert "input 2K" not in sibling
