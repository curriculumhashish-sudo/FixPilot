"""测试对话可视化和事件可视化。"""

import io
import json
import re
import sys
from collections.abc import Sequence
from typing import IO, TYPE_CHECKING, Self, cast
from unittest.mock import MagicMock

from pydantic import Field
from rich.console import Group
from rich.text import Text

from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.visualizer import (
    DefaultConversationVisualizer,
)
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    CondensationRequest,
    ConversationStateUpdateEvent,
    MessageEvent,
    ObservationEvent,
    PauseEvent,
    SystemPromptEvent,
    UserRejectObservation,
)
from openhands.sdk.event.base import Event
from openhands.sdk.event.types import SourceType
from openhands.sdk.llm import (
    Message,
    MessageToolCall,
    ReasoningItemModel,
    TextContent,
)
from openhands.sdk.llm.utils.metrics import Metrics
from openhands.sdk.tool import Action, Observation, ToolDefinition, ToolExecutor


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation


class _UnknownEventForVisualizerTest(Event):
    """用于测试回退方案可视化的事件类型未知。

    此类在模块级别定义（而不是在测试函数内部），以确保它在序列化/反序列化期间可由
    Pydantic 导入。 当与 pytest-xdist 并行运行测试时，在测试函数
    中定义它会导致测试污染。
    """

    source: SourceType = "agent"


class _Cp1252Stdout:
    """再现旧版 Windows cp1252 标准输出编码的最小流。"""

    encoding = "cp1252"

    def __init__(self) -> None:
        self._buffer = io.StringIO()

    def fileno(self) -> int:
        return 1

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return True

    def write(self, text: str) -> int:
        text.encode(self.encoding)
        return self._buffer.write(text)

    def getvalue(self) -> str:
        return self._buffer.getvalue()


class VisualizerMockAction(Action):
    """模拟对象测试操作。"""

    command: str = "test command"
    working_dir: str = "/tmp"


class VisualizerCustomAction(Action):
    """具有重写可视化方法的自定义操作。"""

    task_list: list[dict] = Field(default_factory=list)

    @property
    def visualize(self) -> Text:
        """任务跟踪器的自定义可视化。"""
        content = Text()
        content.append("Task Tracker Action\n", style="bold")
        content.append(f"Tasks: {len(self.task_list)}")
        for i, task in enumerate(self.task_list):
            content.append(f"\n  {i + 1}. {task.get('title', 'Untitled')}")
        return content


class VisualizerMockObservation(Observation):
    """模拟对象观测结果用于测试。"""

    pass


class VisualizerMockExecutor(ToolExecutor):
    """模拟对象用于测试的执行器。"""

    def __call__(
        self,
        action: VisualizerMockAction,
        conversation: "LocalConversation | None" = None,
    ) -> VisualizerMockObservation:
        return VisualizerMockObservation.from_text("test")


class VisualizerMockTool(
    ToolDefinition[VisualizerMockAction, VisualizerMockObservation]
):
    """模拟对象测试工具。"""

    @classmethod
    def create(cls, *args, **kwargs) -> Sequence[Self]:
        return [
            cls(
                description="A test tool for demonstration",
                action_type=VisualizerMockAction,
                observation_type=VisualizerMockObservation,
                executor=VisualizerMockExecutor(),
            )
        ]


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


def subtitle_of(block: Group | None) -> str | None:
    """从事件中提取渲染的指标副标题（标记已去除）
    块，如果该块没有指标副标题，则为 None。"""
    if block is None:
        return None
    for renderable in block.renderables:
        if isinstance(renderable, Text) and renderable.plain.startswith("Tokens:"):
            return renderable.plain
    return None


def test_action_base_visualize():
    """测试 Action 是否具有可视化属性。"""
    action = VisualizerMockAction(command="echo hello", working_dir="/home")

    result = action.visualize
    assert isinstance(result, Text)

    # 检查它是否包含操作名称和字段
    text_content = result.plain
    assert "VisualizerMockAction" in text_content
    assert "command" in text_content
    assert "echo hello" in text_content
    assert "working_dir" in text_content
    assert "/home" in text_content


def test_custom_action_visualize():
    """测试自定义操作是否可以覆盖可视化方法。"""
    tasks = [
        {"title": "Task 1", "status": "todo"},
        {"title": "Task 2", "status": "done"},
    ]
    action = VisualizerCustomAction(task_list=tasks)

    result = action.visualize
    assert isinstance(result, Text)

    text_content = result.plain
    assert "Task Tracker Action" in text_content
    assert "Tasks: 2" in text_content
    assert "1. Task 1" in text_content
    assert "2. Task 2" in text_content


def test_system_prompt_event_visualize():
    """测试 SystemPromptEvent 可视化。"""
    tool = VisualizerMockTool.create()[0]

    event = SystemPromptEvent(
        system_prompt=TextContent(text="You are a helpful assistant."),
        tools=[tool],
    )

    result = event.visualize
    assert isinstance(result, Text)

    text_content = result.plain
    assert "System Prompt:" in text_content
    assert "You are a helpful assistant." in text_content
    assert "Tools Available: 1" in text_content
    assert "visualizer_mock" in text_content


def test_action_event_visualize():
    """测试 ActionEvent 可视化。"""
    action = VisualizerMockAction(command="ls -la", working_dir="/tmp")
    tool_call = create_tool_call("call_123", "terminal", {"command": "ls -la"})
    event = ActionEvent(
        thought=[TextContent(text="I need to list files")],
        reasoning_content="Let me check the directory contents",
        action=action,
        tool_name="terminal",
        tool_call_id="call_123",
        tool_call=tool_call,
        llm_response_id="response_456",
    )

    result = event.visualize
    assert isinstance(result, Text)

    text_content = result.plain
    assert "Reasoning:" in text_content
    assert "Let me check the directory contents" in text_content
    assert "Thought:" in text_content
    assert "I need to list files" in text_content
    assert "VisualizerMockAction" in text_content


def test_action_event_visualize_omits_empty_responses_reasoning_label():
    """空响应推理项不应呈现推理标题。"""
    action = VisualizerMockAction(command="ls -la", working_dir="/tmp")
    tool_call = create_tool_call("call_123", "terminal", {"command": "ls -la"})
    event = ActionEvent(
        thought=[],
        responses_reasoning_item=ReasoningItemModel(),
        action=action,
        tool_name="terminal",
        tool_call_id="call_123",
        tool_call=tool_call,
        llm_response_id="response_456",
    )

    text_content = event.visualize.plain

    assert "Reasoning:" not in text_content
    assert "ls -la" in text_content


def test_action_event_visualize_renders_responses_reasoning_content():
    """推理明文的响应在存在时仍应呈现。"""
    action = VisualizerMockAction(command="ls -la", working_dir="/tmp")
    tool_call = create_tool_call("call_123", "terminal", {"command": "ls -la"})
    event = ActionEvent(
        thought=[],
        responses_reasoning_item=ReasoningItemModel(
            summary=["Check the directory first"]
        ),
        action=action,
        tool_name="terminal",
        tool_call_id="call_123",
        tool_call=tool_call,
        llm_response_id="response_456",
    )

    text_content = event.visualize.plain

    assert "Reasoning:" in text_content
    assert "Check the directory first" in text_content
    assert "ls -la" in text_content


def test_observation_event_visualize():
    """测试 ObservationEvent 可视化。"""
    observation = VisualizerMockObservation(
        content=[TextContent(text="total 4\ndrwxr-xr-x 2 user user 4096 Jan 1 12:00 .")]
    )
    event = ObservationEvent(
        observation=observation,
        action_id="action_123",
        tool_name="terminal",
        tool_call_id="call_123",
    )

    result = event.visualize
    assert isinstance(result, Text)

    text_content = result.plain
    assert "Tool: terminal" in text_content
    assert "Result:" in text_content
    assert "total 4" in text_content


def test_message_event_visualize():
    """测试 MessageEvent 可视化。"""
    message = Message(
        role="user",
        content=[TextContent(text="Hello, how can you help me?")],
    )
    event = MessageEvent(
        source="user",
        llm_message=message,
        activated_skills=["helper", "analyzer"],
        extended_content=[TextContent(text="Additional context")],
    )

    result = event.visualize
    assert isinstance(result, Text)

    text_content = result.plain
    assert "Hello, how can you help me?" in text_content
    assert "Activated Skills: helper, analyzer" in text_content
    assert "Prompt Extension based on Agent Context:" in text_content
    assert "Additional context" in text_content


def test_message_event_visualize_omits_empty_responses_reasoning_label():
    """空响应推理项不应呈现推理标题。"""
    message = Message(
        role="assistant",
        content=[TextContent(text="Hello, how can you help me?")],
        responses_reasoning_item=ReasoningItemModel(),
    )
    event = MessageEvent(source="agent", llm_message=message)

    text_content = event.visualize.plain

    assert "Reasoning:" not in text_content
    assert "Hello, how can you help me?" in text_content


def test_environment_user_role_message_is_not_titled_as_human_user():
    """框架用户角色消息不应呈现为人工创作的输入。"""
    from rich.console import Console

    visualizer = DefaultConversationVisualizer()
    event = MessageEvent(
        source="environment",
        llm_message=Message(
            role="user",
            content=[TextContent(text="Framework corrective nudge.")],
        ),
    )

    block = visualizer._create_event_block(event)
    assert block is not None

    console = Console()
    with console.capture() as capture:
        console.print(block)
    output = capture.get()

    assert "Message from User" not in output
    assert "Message from Environment" in output
    assert "Framework corrective nudge." in output


def test_skip_user_messages_keeps_environment_user_role_messages():
    """skip_user_messages 应该只跳过真实的人类消息。"""
    visualizer = DefaultConversationVisualizer(skip_user_messages=True)
    human_event = MessageEvent(
        source="user",
        llm_message=Message(
            role="user",
            content=[TextContent(text="Human input")],
        ),
    )
    environment_event = MessageEvent(
        source="environment",
        llm_message=Message(
            role="user",
            content=[TextContent(text="Framework corrective nudge.")],
        ),
    )

    assert visualizer._create_event_block(human_event) is None
    assert visualizer._create_event_block(environment_event) is not None


def test_agent_error_event_visualize():
    """测试 AgentErrorEvent 可视化。"""
    event = AgentErrorEvent(
        error="Failed to execute command: permission denied",
        tool_call_id="call_err_1",
        tool_name="terminal",
    )

    result = event.visualize
    assert isinstance(result, Text)

    text_content = result.plain
    assert "Error Details:" in text_content
    assert "Failed to execute command: permission denied" in text_content


def test_pause_event_visualize():
    """测试 PauseEvent 可视化。"""
    event = PauseEvent()

    result = event.visualize
    assert isinstance(result, Text)

    text_content = result.plain
    assert "Conversation Paused" in text_content


def test_conversation_visualizer_initialization():
    """测试DefaultConversationVisualizer可以初始化。"""
    visualizer = DefaultConversationVisualizer()
    assert visualizer is not None
    assert hasattr(visualizer, "on_event")
    assert hasattr(visualizer, "_create_event_block")


def test_default_visualizer_handles_unicode_on_legacy_windows_stdout(monkeypatch):
    """可视化工具输出在旧版 Windows 标准输出上不应失败。"""
    stream = _Cp1252Stdout()
    monkeypatch.setattr(sys, "stdout", cast(IO[str], stream))

    visualizer = DefaultConversationVisualizer()
    event = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant",
            content=[TextContent(text="\U0001f510 Security Policy")],
        ),
    )

    visualizer.on_event(event)

    assert "Security Policy" in stream.getvalue()


def test_visualizer_event_panel_creation():
    """测试可视化工具是否为不同的事件类型创建事件块。"""
    from rich.console import Group

    conv_viz = DefaultConversationVisualizer()

    # 使用简单的动作事件进行测试
    action = VisualizerMockAction(command="test")
    tool_call = create_tool_call("call_1", "test", {})
    action_event = ActionEvent(
        thought=[TextContent(text="Testing")],
        action=action,
        tool_name="test",
        tool_call_id="call_1",
        tool_call=tool_call,
        llm_response_id="response_1",
    )
    block = conv_viz._create_event_block(action_event)
    assert block is not None
    assert isinstance(block, Group)


def test_visualizer_action_event_with_none_action_panel():
    """ActionEvent 与 action=None 应呈现为“智能体操作（未执行）”。"""
    import re

    from rich.console import Console

    visualizer = DefaultConversationVisualizer()
    tc = create_tool_call("call_ne_1", "missing_fn", {})
    action_event = ActionEvent(
        thought=[TextContent(text="...")],
        tool_call=tc,
        tool_name=tc.name,
        tool_call_id=tc.id,
        llm_response_id="resp_viz_1",
        action=None,
    )
    block = visualizer._create_event_block(action_event)
    assert block is not None

    # 将块渲染为字符串以检查内容
    console = Console()
    with console.capture() as capture:
        console.print(block)
    output = capture.get()

    # 剥离ANSI代码进行文本比较
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    plain_output = ansi_escape.sub("", output)

    # 确保它不会回落到 UNKNOWN
    assert "UNKNOWN Event" not in plain_output
    # 并使用“智能体操作（未执行）”标题
    assert "Agent Action (Not Executed)" in plain_output


def test_visualizer_user_reject_observation_panel():
    """UserRejectObservation 应该渲染一个专用的事件块。"""
    from rich.console import Console

    visualizer = DefaultConversationVisualizer()
    event = UserRejectObservation(
        tool_name="demo_tool",
        tool_call_id="fc_call_1",
        action_id="action_1",
        rejection_reason="User rejected the proposed action.",
    )

    block = visualizer._create_event_block(event)
    assert block is not None

    # 将块渲染为字符串以检查内容
    console = Console()
    with console.capture() as capture:
        console.print(block)
    output = capture.get()

    assert "UNKNOWN Event" not in output
    assert "User Rejected Action" in output
    # 确保原因是渲染文本的一部分
    assert "User rejected the proposed action." in output


def test_visualizer_condensation_request_panel():
    """CondensationRequest 用友好的文本呈现系统风格的事件块。"""
    from rich.console import Console

    visualizer = DefaultConversationVisualizer()
    event = CondensationRequest()
    block = visualizer._create_event_block(event)
    assert block is not None

    # 将块渲染为字符串以检查内容
    console = Console()
    with console.capture() as capture:
        console.print(block)
    output = capture.get()

    # 不应回退到 UNKNOWN
    assert "UNKNOWN Event" not in output
    # 标题应注明上下文压缩请求
    assert "Condensation Request" in output
    # 正文应该是友好的可视化文本
    assert "Conversation Condensation Requested" in output
    assert "condensation of the conversation history" in output


def test_metrics_formatting():
    """测试指标字幕格式。"""
    from unittest.mock import MagicMock

    from openhands.sdk.conversation.conversation_stats import ConversationStats
    from openhands.sdk.llm.utils.metrics import Metrics

    # 使用指标创建对话统计数据
    conversation_stats = ConversationStats()

    # 创建指标并添加到对话统计信息
    metrics = Metrics(model_name="test-model")
    metrics.add_cost(0.0234)
    metrics.add_token_usage(
        prompt_tokens=1500,
        completion_tokens=500,
        cache_read_tokens=300,
        cache_write_tokens=0,
        reasoning_tokens=200,
        context_window=8000,
        response_id="test_response",
    )

    # 将指标添加到对话统计信息
    conversation_stats.usage_to_metrics["test_usage"] = metrics

    # 创建可视化工具并使用模拟对象状态进行初始化
    visualizer = DefaultConversationVisualizer()
    mock_state = MagicMock()
    mock_state.stats = conversation_stats
    visualizer.initialize(mock_state)

    # 测试指标字幕格式
    subtitle = visualizer._format_metrics_subtitle()
    assert subtitle is not None
    assert "1.5K" in subtitle  # 输入 token 缩写（删除尾随零）
    assert "500" in subtitle  # 输出token
    assert "20.00%" in subtitle  # 缓存命中率
    assert "200" in subtitle  # 推理 token
    assert "0.0234" in subtitle  # 成本


def test_metrics_subtitle_caps_cache_rate_when_cache_exceeds_prompt():
    """回归对于 #3044：ACP 报告 input_tokens 不包括缓存读取，
    所以 cache_read_tokens 可以超过 prompt_tokens。 渲染的缓存命中率必须保持在 [0,
    100]% 范围内。
    """
    stats = ConversationStats()
    metrics = Metrics(model_name="test-model")
    # 从该问题中复制的数字：13 个输入 + ~117,654 个缓存，之前呈现为“缓存命中 905030.77%”
    # 。
    #
    metrics.add_token_usage(
        prompt_tokens=13,
        completion_tokens=568,
        cache_read_tokens=117_654,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=200_000,
        response_id="acp_response",
    )
    stats.usage_to_metrics["acp_usage"] = metrics

    visualizer = DefaultConversationVisualizer()
    mock_state = MagicMock()
    mock_state.stats = stats
    visualizer.initialize(mock_state)

    subtitle = visualizer._format_metrics_subtitle()
    assert subtitle is not None
    match = re.search(r"cache hit (?:\(total )?([\d.]+)%", subtitle)
    assert match, subtitle
    rate = float(match.group(1))
    assert 0.0 <= rate <= 100.0, f"cache hit rate {rate} outside [0, 100]"


def test_metrics_abbreviation_formatting():
    """具有各种边缘情况的测试编号缩写。"""
    from unittest.mock import MagicMock

    from openhands.sdk.conversation.conversation_stats import ConversationStats
    from openhands.sdk.llm.utils.metrics import Metrics

    test_cases = [
        # (input_tokens, expected_abbr)
        (999, "999"),  # 低于阈值
        (1000, "1K"),  # 精确的 K 边界，删除尾随零
        (1500, "1.5K"),  # K 保留一位小数，删除尾随零
        (89080, "89.08K"),  # K 具有两位小数（回归测试 bug）
        (89000, "89K"),  # K 删除了尾随零
        (1000000, "1M"),  # 精确的 M 边界
        (1234567, "1.23M"),  # M 带小数
        (1000000000, "1B"),  # 精确 B 边界
    ]

    for tokens, expected in test_cases:
        stats = ConversationStats()
        metrics = Metrics(model_name="test-model")
        metrics.add_token_usage(
            prompt_tokens=tokens,
            completion_tokens=100,
            cache_read_tokens=0,
            cache_write_tokens=0,
            reasoning_tokens=0,
            context_window=8000,
            response_id="test",
        )
        stats.usage_to_metrics["test"] = metrics

        visualizer = DefaultConversationVisualizer()
        mock_state = MagicMock()
        mock_state.stats = stats
        visualizer.initialize(mock_state)
        subtitle = visualizer._format_metrics_subtitle()

        assert subtitle is not None, f"Failed for {tokens}"
        assert expected in subtitle, (
            f"Expected '{expected}' in subtitle for {tokens}, got: {subtitle}"
        )


def test_metrics_subtitle_shows_per_request_and_cumulative():
    """对同一个 LLM 的两个连续请求：最新的字幕
    事件应该显示每个请求的使用情况和运行的累积总数，而不仅仅是总数（#4105）。
    """
    stats = ConversationStats()
    metrics = Metrics(model_name="test-model")
    metrics.add_token_usage(
        prompt_tokens=4390,
        completion_tokens=144,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="response_1",
    )
    metrics.add_token_usage(
        prompt_tokens=4630,
        completion_tokens=114,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="response_2",
    )
    stats.usage_to_metrics["agent"] = metrics

    visualizer = DefaultConversationVisualizer()
    mock_state = MagicMock()
    mock_state.stats = stats
    visualizer.initialize(mock_state)

    tool_call = create_tool_call("call_1", "test", {})
    event = ActionEvent(
        thought=[TextContent(text="Testing")],
        action=VisualizerMockAction(command="test"),
        tool_name="test",
        tool_call_id="call_1",
        tool_call=tool_call,
        llm_response_id="response_2",
    )

    subtitle = visualizer._format_metrics_subtitle(event)
    # 全字符串断言确定每个请求的数字与实际的数字。 累积——除了交换的数字之外，单独的
    # `in subtitle` 检查无法区分“输入 4.63K（总计 9.02K）”。
    #
    assert subtitle == (
        "Tokens: [cyan]↑ input 4.63K (total 9.02K)[/cyan] • "
        "[magenta]cache hit 0.00% (total 0.00%)[/magenta] • "
        "[blue]↓ output 114 (total 258)[/blue] • "
        "[green]$ (total 0.00)[/green]"
    )


def test_metrics_subtitle_reasoning_and_cache_hit_are_per_request():
    """Regression: 推理token和缓存命中率必须相同
    每个请求“X（总 Y）”处理为输入/输出 token。 在旁边显示按次请求输入/输出数量的累积
    推理计数，这读起来和按次请求的输入/输出数量一样，这是混淆 #4105
     要解决的问题。
    """
    stats = ConversationStats()
    metrics = Metrics(model_name="test-model")
    metrics.add_token_usage(
        prompt_tokens=1000,
        completion_tokens=100,
        cache_read_tokens=100,
        cache_write_tokens=0,
        reasoning_tokens=200,
        context_window=8000,
        response_id="response_1",
    )
    metrics.add_token_usage(
        prompt_tokens=2000,
        completion_tokens=200,
        cache_read_tokens=1000,
        cache_write_tokens=0,
        reasoning_tokens=50,
        context_window=8000,
        response_id="response_2",
    )
    stats.usage_to_metrics["agent"] = metrics

    visualizer = DefaultConversationVisualizer()
    mock_state = MagicMock()
    mock_state.stats = stats
    visualizer.initialize(mock_state)

    tool_call = create_tool_call("call_1", "test", {})
    event = ActionEvent(
        thought=[TextContent(text="Testing")],
        action=VisualizerMockAction(command="test"),
        tool_name="test",
        tool_call_id="call_1",
        tool_call=tool_call,
        llm_response_id="response_2",
    )

    subtitle = visualizer._format_metrics_subtitle(event)
    assert subtitle is not None
    # 每个请求推理（仅限 response_2：50），而不是累计 250。
    assert "reasoning 50 (total 250)" in subtitle
    # 每个请求的缓存命中率 (1000 / 2000)，而不是累积率。
    assert "cache hit 50.00% (total 36.67%)" in subtitle


def test_metrics_subtitle_matches_by_response_id_not_last_index():
    """Regression: get_combined_metrics().token_usages[-1] 合并用法
    跨每个使用 ID（智能体、上下文压缩器、...），并且不按时间顺序排列。 每个请求的使用
    情况必须通过 response_id 查找，遥测设置为与
    llm_response_id 携带的相同 id 事件 (#4105)。
    """
    stats = ConversationStats()

    # 上下文压缩器使用 ID 首先插入...
    condenser_metrics = Metrics(model_name="test-model")
    condenser_metrics.add_token_usage(
        prompt_tokens=2000,
        completion_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="condenser_response",
    )
    stats.usage_to_metrics["condenser"] = condenser_metrics

    # ...then the agent usage id, which lands last in the merged list.
    agent_metrics = Metrics(model_name="test-model")
    agent_metrics.add_token_usage(
        prompt_tokens=999,
        completion_tokens=9,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=8000,
        response_id="agent_response",
    )
    stats.usage_to_metrics["agent"] = agent_metrics

    # 健全性检查：天真的 token_usages[-1] 将返回智能体用法，而不是此测试查找的上下文压缩
    # 器用法。
    #
    combined = stats.get_combined_metrics()
    assert combined.token_usages[-1].response_id == "agent_response"

    visualizer = DefaultConversationVisualizer()
    mock_state = MagicMock()
    mock_state.stats = stats
    visualizer.initialize(mock_state)

    tool_call = create_tool_call("call_1", "test", {})
    event = ActionEvent(
        thought=[TextContent(text="Testing")],
        action=VisualizerMockAction(command="test"),
        tool_name="test",
        tool_call_id="call_1",
        tool_call=tool_call,
        llm_response_id="condenser_response",
    )

    request_usage = visualizer._find_request_usage(event)
    assert request_usage is not None
    assert request_usage.prompt_tokens == 2000
    assert request_usage.completion_tokens == 50


def test_metrics_subtitle_fallback_labels_totals():
    """无事件，或 response_id 未知的事件 (e.g. ACP 路径，
    其中响应 ID 是每个会话），必须将每个数字标记为“（总计）”：每个请求事件旁边的裸数
    字读取为每个请求，这是 #4105 想要解决的混乱。
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

    visualizer = DefaultConversationVisualizer()
    mock_state = MagicMock()
    mock_state.stats = stats
    visualizer.initialize(mock_state)

    expected = (
        "Tokens: [cyan]↑ input (total 1K)[/cyan] • "
        "[magenta]cache hit (total 0.00%)[/magenta] • "
        "[blue]↓ output (total 100)[/blue] • "
        "[green]$ (total 0.00)[/green]"
    )

    # 根本没有任何事件。
    assert visualizer._format_metrics_subtitle() == expected

    # 事件带有与任何记录的使用情况都不匹配的 response_id。
    tool_call = create_tool_call("call_1", "test", {})
    event = ActionEvent(
        thought=[TextContent(text="Testing")],
        action=VisualizerMockAction(command="test"),
        tool_name="test",
        tool_call_id="call_1",
        tool_call=tool_call,
        llm_response_id="unknown_response",
    )
    assert visualizer._format_metrics_subtitle(event) == expected


def test_metrics_subtitle_user_message_labels_totals():
    """用户MessageEvents没有携带llm_response_id，因此他们的字幕只能
    显示运行总计——并且必须这样说，而不是打印裸露的数字。"""
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

    visualizer = DefaultConversationVisualizer()
    mock_state = MagicMock()
    mock_state.stats = stats
    visualizer.initialize(mock_state)

    user_event = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Hello")]),
    )
    assert visualizer._format_metrics_subtitle(user_event) == (
        "Tokens: [cyan]↑ input (total 1K)[/cyan] • "
        "[magenta]cache hit (total 0.00%)[/magenta] • "
        "[blue]↓ output (total 100)[/blue] • "
        "[green]$ (total 0.00)[/green]"
    )


def _batch_action_event(call_id: str, response_id: str) -> ActionEvent:
    """为给定的工具调用和 LLM 响应构建 ActionEvent。"""
    return ActionEvent(
        thought=[TextContent(text="Testing")],
        action=VisualizerMockAction(command="test"),
        tool_name="test",
        tool_call_id=call_id,
        tool_call=create_tool_call(call_id, "test", {}),
        llm_response_id=response_id,
    )


def test_claim_batch_primary_tracks_consecutive_batches():
    """并行工具调用共用一个llm_response_id，连续渲染；
    只有每个批次的第一个 ActionEvent 声明每个请求的指标 (#4189)。 检测仅跟踪先前的响
    应 ID - O(1)，不扫描 - 因此必须按渲染顺序对每个事
    件调用一次。
    """
    visualizer = DefaultConversationVisualizer()

    a1 = _batch_action_event("call_1", "resp_batch")
    a2 = _batch_action_event("call_2", "resp_batch")
    a3 = _batch_action_event("call_3", "resp_batch")
    b1 = _batch_action_event("call_4", "resp_other")
    b2 = _batch_action_event("call_5", "resp_other")

    # 每个响应 ID 的第一个 ActionEvent 是其批次的主响应 ID。
    assert visualizer._claim_batch_primary(a1) is True
    assert visualizer._claim_batch_primary(a2) is False
    assert visualizer._claim_batch_primary(a3) is False
    # 新的响应 ID 再次启动新批次 -> 主批次。
    assert visualizer._claim_batch_primary(b1) is True

    # 非 ActionEvents 永远不会形成工具调用批次，也不会干扰跟踪：仍然会检测到它们之后的
    # resp_other 同级。
    #
    user_event = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="hi")]),
    )
    assert visualizer._claim_batch_primary(user_event) is True
    assert visualizer._claim_batch_primary(b2) is False


def test_parallel_batch_only_primary_shows_per_request():
    """端到端通过 _create_event_block：在并行工具调用批处理中
    （共享 llm_response_id）仅第一个事件显示每个请求的数量； 兄弟姐妹退回到仅总计，因
    此共享使用不会重复 N 次 (#4189)。
    """
    stats = ConversationStats()
    metrics = Metrics(model_name="test-model")
    # 之前的一个请求，因此运行总和（3K/300）与这次批次的每请求使用量（2K/200）不同，两个
    # 值在输出中是可区分的。
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

    a1 = _batch_action_event("call_1", "resp_batch")
    a2 = _batch_action_event("call_2", "resp_batch")
    a3 = _batch_action_event("call_3", "resp_batch")

    visualizer = DefaultConversationVisualizer()
    mock_state = MagicMock()
    mock_state.stats = stats
    visualizer.initialize(mock_state)

    # 按流顺序渲染。 主要：每个请求的数量以及总数。
    assert subtitle_of(visualizer._create_event_block(a1)) == (
        "Tokens: ↑ input 2K (total 3K) • cache hit 0.00% (total 0.00%) • "
        "↓ output 200 (total 300) • $ (total 0.00)"
    )
    # 兄弟姐妹：仅总计，因此相同的 2K/200 不会显示三次。
    sibling = (
        "Tokens: ↑ input (total 3K) • cache hit (total 0.00%) • "
        "↓ output (total 300) • $ (total 0.00)"
    )
    assert subtitle_of(visualizer._create_event_block(a2)) == sibling
    assert subtitle_of(visualizer._create_event_block(a3)) == sibling


def test_event_base_fallback_visualize():
    """测试事件是否提供回退方案可视化。"""
    event = _UnknownEventForVisualizerTest()
    result = event.visualize
    assert isinstance(result, Text)

    text_content = result.plain
    assert "Unknown event type: _UnknownEventForVisualizerTest" in text_content


def test_conversation_error_event_visualize():
    """测试 ConversationErrorEvent 是否提供特定的可视化。"""
    from openhands.sdk.event.conversation_error import ConversationErrorEvent

    event = ConversationErrorEvent(
        source="environment",
        code="TestError",
        detail="Something went wrong",
    )
    text_content = event.visualize.plain

    assert "Unknown event type:" not in text_content
    assert "Conversation Error" in text_content
    assert "TestError" in text_content
    assert "Something went wrong" in text_content


def test_visualizer_conversation_state_update_event_skipped():
    """测试 ConversationStateUpdateEvent 未可视化。"""
    visualizer = DefaultConversationVisualizer()
    event = ConversationStateUpdateEvent(key="execution_status", value="finished")

    block = visualizer._create_event_block(event)
    # 应返回 None 以跳过可视化
    assert block is None


def test_default_visualizer_create_sub_visualizer_returns_none():
    """测试 DefaultConversationVisualizer.create_sub_visualizer 返回 None。

    这是预期的默认行为 - 基础可视化工具不支持子智能体可视化。 像 DelegationVisualizer
     这样的子类可以覆盖它以提供子智能体可视化工具。
    """
    visualizer = DefaultConversationVisualizer()
    result = visualizer.create_sub_visualizer("test_agent")
    assert result is None
