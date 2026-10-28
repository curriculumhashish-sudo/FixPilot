import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, TextIO, cast

from pydantic import BaseModel
from rich.console import Console, Group
from rich.rule import Rule
from rich.text import Text

from openhands.sdk.conversation.visualizer.base import (
    ConversationVisualizerBase,
)
from openhands.sdk.event import (
    ACPToolCallEvent,
    ActionEvent,
    AgentErrorEvent,
    ConversationStateUpdateEvent,
    MessageEvent,
    ObservationEvent,
    PauseEvent,
    SystemPromptEvent,
    UserRejectObservation,
)
from openhands.sdk.event.base import Event
from openhands.sdk.event.condenser import Condensation, CondensationRequest
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage


logger = logging.getLogger(__name__)


# 这些是外部输入
_OBSERVATION_COLOR = "yellow"
_MESSAGE_USER_COLOR = "gold3"
_PAUSE_COLOR = "bright_yellow"
# 这些是内部系统的东西
_SYSTEM_COLOR = "magenta"
_THOUGHT_COLOR = "bright_black"
_ERROR_COLOR = "red"
# 这些是智能体个操作
_ACTION_COLOR = "blue"
_MESSAGE_ASSISTANT_COLOR = _ACTION_COLOR

_MESSAGE_SOURCE_TITLES = {
    "agent": "Message from Agent",
    "user": "Message from User",
    "environment": "Message from Environment",
    "hook": "Message from Hook",
}
_MESSAGE_SOURCE_COLORS = {
    "agent": _MESSAGE_ASSISTANT_COLOR,
    "user": _MESSAGE_USER_COLOR,
    "environment": _SYSTEM_COLOR,
    "hook": _SYSTEM_COLOR,
}

DEFAULT_HIGHLIGHT_REGEX = {
    r"^Reasoning:": f"bold {_THOUGHT_COLOR}",
    r"^Thought:": f"bold {_THOUGHT_COLOR}",
    r"^Action:": f"bold {_ACTION_COLOR}",
    r"^Arguments:": f"bold {_ACTION_COLOR}",
    r"^Tool:": f"bold {_OBSERVATION_COLOR}",
    r"^Result:": f"bold {_OBSERVATION_COLOR}",
    r"^Rejection Reason:": f"bold {_ERROR_COLOR}",
    # Markdown-风格
    r"\*\*(.*?)\*\*": "bold",
    r"\*(.*?)\*": "italic",
}


@dataclass(slots=True)
class _EncodingSafeTextIO:
    """文本流包装器，用于替换标准输出不支持的字符。"""

    _stream: TextIO

    @property
    def encoding(self) -> str | None:
        return self._stream.encoding

    def fileno(self) -> int:
        return self._stream.fileno()

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    def write(self, text: str) -> int:
        encoding = self.encoding
        if encoding:
            try:
                text.encode(encoding)
            except UnicodeEncodeError:
                text = text.encode(encoding, errors="replace").decode(encoding)
        return self._stream.write(text)


def _create_console() -> Console:
    stdout = getattr(sys.stdout, "rich_proxied_file", sys.stdout)
    return Console(file=cast(IO[str], _EncodingSafeTextIO(cast(TextIO, stdout))))


class EventVisualizationConfig(BaseModel):
    """用于如何可视化事件类型的配置。"""

    title: str | Callable[[Event], str]
    """为此事件显示的标题。 可以是字符串或可调用的。"""

    color: str | Callable[[Event], str]
    """用于标题和规则的丰富颜色。 可以是字符串或可调用的。"""

    show_metrics: bool = False
    """是否显示指标副标题。"""

    indent_content: bool = False
    """是否缩进内容。"""

    skip: bool = False
    """如果 True，则完全跳过此事件类型的可视化。"""

    model_config = {"arbitrary_types_allowed": True}


def indent_content(content: Text, spaces: int = 4) -> Text:
    """缩进视觉层次结构的内容，同时保留所有格式。"""
    prefix = " " * spaces
    lines = content.split("\n")

    indented = Text()
    for i, line in enumerate(lines):
        if i > 0:
            indented.append("\n")
        indented.append(prefix)
        indented.append(line)

    return indented


def section_header(title: str, color: str) -> Rule:
    """创建带有标题的语义分隔线。"""
    return Rule(
        f"[{color} bold]{title}[/{color} bold]",
        style=color,
        characters="─",
        align="left",
    )


def build_event_block(
    content: Text,
    title: str,
    title_color: str,
    subtitle: str | None = None,
    indent: bool = False,
) -> Group:
    """构建一个包含标题、内容和可选副标题的完整事件块。"""
    parts = []

    # 带规则的标题
    parts.append(section_header(title, title_color))
    parts.append(Text())  # 标题后空行

    # 内容（可选缩进）
    if indent:
        parts.append(indent_content(content))
    else:
        parts.append(content)

    # 副标题（指标）（如果提供）
    if subtitle:
        parts.append(Text())  # 字幕前空行
        subtitle_text = Text.from_markup(subtitle)
        subtitle_text.stylize("dim")
        parts.append(subtitle_text)

    parts.append(Text())  # 块后空行

    return Group(*parts)


def _get_action_title(event: Event) -> str:
    """根据操作是否为 None 获取 ActionEvent 的标题。"""
    if isinstance(event, ActionEvent):
        return "Agent Action (Not Executed)" if event.action is None else "Agent Action"
    return "Action"


def _get_message_title(event: Event) -> str:
    """根据事件归因获取 MessageEvent 的标题。"""
    if isinstance(event, MessageEvent) and event.llm_message:
        return _MESSAGE_SOURCE_TITLES[event.source]
    return "Message"


def _get_message_color(event: Event) -> str:
    """根据事件归因获取 MessageEvent 的颜色。"""
    if isinstance(event, MessageEvent) and event.llm_message:
        return _MESSAGE_SOURCE_COLORS[event.source]
    return "white"


# 事件类型到可视化配置映射这用更清晰的查找方法替换了大型 isinstance 链
#
EVENT_VISUALIZATION_CONFIG: dict[type[Event], EventVisualizationConfig] = {
    ACPToolCallEvent: EventVisualizationConfig(
        title="ACP Tool Call",
        color=_ACTION_COLOR,
    ),
    SystemPromptEvent: EventVisualizationConfig(
        title="System Prompt",
        color=_SYSTEM_COLOR,
    ),
    ActionEvent: EventVisualizationConfig(
        title=_get_action_title,
        color=_ACTION_COLOR,
        show_metrics=True,
    ),
    ObservationEvent: EventVisualizationConfig(
        title="Observation",
        color=_OBSERVATION_COLOR,
    ),
    UserRejectObservation: EventVisualizationConfig(
        title="User Rejected Action",
        color=_ERROR_COLOR,
    ),
    MessageEvent: EventVisualizationConfig(
        title=_get_message_title,
        color=_get_message_color,
        show_metrics=True,
    ),
    AgentErrorEvent: EventVisualizationConfig(
        title="Agent Error",
        color=_ERROR_COLOR,
        show_metrics=True,
    ),
    PauseEvent: EventVisualizationConfig(
        title="User Paused",
        color=_PAUSE_COLOR,
    ),
    Condensation: EventVisualizationConfig(
        title="Condensation",
        color="white",
        show_metrics=True,
    ),
    CondensationRequest: EventVisualizationConfig(
        title="Condensation Request",
        color=_SYSTEM_COLOR,
    ),
    ConversationStateUpdateEvent: EventVisualizationConfig(
        title="Conversation State Update",
        color=_SYSTEM_COLOR,
        skip=True,
    ),
}


class DefaultConversationVisualizer(ConversationVisualizerBase):
    """使用丰富的格式处理对话事件的可视化。

    提供具有语义分隔符和完整内容显示的丰富格式输出。
    """

    _console: Console
    _skip_user_messages: bool
    _highlight_patterns: dict[str, str]

    def __init__(
        self,
        highlight_regex: dict[str, str] | None = DEFAULT_HIGHLIGHT_REGEX,
        skip_user_messages: bool = False,
    ):
        """初始化可视化工具。

        Args:
            highlight_regex: 将正则表达式模式映射到丰富颜色样式的字典
                           用于在可视化工具中突出显示关键字。 例如：{“推理：”：“粗体
                           蓝色”，“思想：”：“粗体绿色”}
            skip_user_messages: 如果为 True，则跳过显示用户消息。 有用于
                                用户输入与显示无关的场景。
        """
        super().__init__()
        self._console = _create_console()
        self._skip_user_messages = skip_user_messages
        self._highlight_patterns = highlight_regex or {}
        # 上一个 ActionEvent 的响应 ID； ``_claim_batch_primary`` 使用它来发现并行工具调
        # 用同级 (#4189)。
        #
        self._last_action_response_id: str | None = None

    def on_event(self, event: Event) -> None:
        """显示具有丰富格式的事件的主事件处理程序。"""
        output = self._create_event_block(event)
        if output:
            self._console.print(output)

    def _apply_highlighting(self, text: Text) -> Text:
        """将基于正则表达式的突出显示应用于文本内容。

        Args:
            text: 要突出显示的富文本对象

        Returns:
            应用了突出显示的新文本对象
        """
        if not self._highlight_patterns:
            return text

        # 创建副本以避免修改原始内容
        highlighted = text.copy()

        # 使用 Rich 的内置 highlight_regex 方法应用每个模式
        for pattern, style in self._highlight_patterns.items():
            pattern_compiled = re.compile(pattern, re.MULTILINE)
            highlighted.highlight_regex(pattern_compiled, style)

        return highlighted

    def _create_event_block(self, event: Event) -> Group | None:
        """为具有完整详细信息的事件创建丰富的事件块。"""
        # 查找此事件类型的可视化配置
        config = EVENT_VISUALIZATION_CONFIG.get(type(event))

        if not config:
            # 警告未知事件类型并跳过
            logger.warning(
                "Event type %s is not registered in EVENT_VISUALIZATION_CONFIG. "
                "Skipping visualization.",
                event.__class__.__name__,
            )
            return None

        # 检查是否应跳过此事件类型
        if config.skip:
            return None

        # 检查我们是否应该根据运行时配置跳过用户消息
        if (
            self._skip_user_messages
            and isinstance(event, MessageEvent)
            and event.llm_message
            and event.source == "user"
        ):
            return None

        # 使用事件的可视化属性来显示内容
        content = event.visualize

        if not content.plain.strip():
            return None

        # 如果已配置，则应用突出显示
        if self._highlight_patterns:
            content = self._apply_highlighting(content)

        # 解析标题（可以是字符串或可调用的）
        title = config.title(event) if callable(config.title) else config.title

        # 解析颜色（可以是字符串或可调用）
        title_color = config.color(event) if callable(config.color) else config.color

        # 如果需要，构建字幕。 并行工具调用批处理的同级会回退到仅总计，因此不会重复共享
        # 的每个请求使用情况。
        #
        subtitle = (
            self._format_metrics_subtitle(
                event, force_totals=not self._claim_batch_primary(event)
            )
            if config.show_metrics
            else None
        )

        return build_event_block(
            content=content,
            title=title,
            title_color=title_color,
            subtitle=subtitle,
        )

    def _find_request_usage(self, event: Event | None) -> TokenUsage | None:
        """查找生成 ``event`` 的 LLM 请求的 TokenUsage。

        匹配 ``TokenUsage.response_id``，不在列表位置：遥测记录
        ``TokenUsage.response_id = resp.id``
         和事件携带
        ``llm_response_id = llm_response.id``，与大多数 LLM 路径对齐。 不过，这种通信
        并不总是可靠的——ACP路径记录一个
        ``response_id``，而不是一个请求，因此它在这里无法匹配，调用者会 fallback到累
        积格式。 我们故意不使用
        ``get_combined_metrics().token_usages[-1]`` 因为该列表合并了每个用法 ID（智能
        体、上下文压缩器、...）的用法
        ，并且它们之间不按时间顺序排列。
        """
        if not isinstance(event, (ActionEvent, MessageEvent, Condensation)):
            return None

        response_id = event.llm_response_id
        if not response_id:
            return None

        if not (stats := self.conversation_stats):
            return None

        return next(
            (
                usage
                for metrics in stats.usage_to_metrics.values()
                for usage in reversed(metrics.token_usages)
                if usage.response_id == response_id
            ),
            None,
        )

    def _claim_batch_primary(self, event: Event | None) -> bool:
        """``event`` 是否是其 LLM 响应的第一个 ActionEvent。

        并行工具调用共享一个 ``llm_response_id`` 和每个请求一个
        ``TokenUsage``; 将其显示在每个同级下读取为 N 个单独的请求（#4189），因此只有
        第一个“声明”每个请求的编号。 有状态——按渲染顺序每个
        事件调用一次。 批次连续渲染，因此跟踪先前的响应 ID 就足够了 (O(1))。
        """
        if not isinstance(event, ActionEvent):
            return True

        is_primary = event.llm_response_id != self._last_action_response_id
        self._last_action_response_id = event.llm_response_id
        return is_primary

    def _format_metrics_subtitle(
        self, event: Event | None = None, *, force_totals: bool = False
    ) -> str | None:
        """将 LLM 指标格式化为带有图标的视觉上吸引人的字幕字符串，
        使用对话统计数据的颜色和 k/m 缩写。"""
        stats = self.conversation_stats
        if not stats:
            return None

        combined_metrics = stats.get_combined_metrics()
        if not combined_metrics or not combined_metrics.accumulated_token_usage:
            return None

        usage = combined_metrics.accumulated_token_usage
        cost = combined_metrics.accumulated_cost or 0.0

        # 助手：1234 ->“1.2K”，1200000 ->“1.2M”
        def abbr(n: int | float) -> str:
            n = int(n or 0)
            if n >= 1_000_000_000:
                val, suffix = n / 1_000_000_000, "B"
            elif n >= 1_000_000:
                val, suffix = n / 1_000_000, "M"
            elif n >= 1_000:
                val, suffix = n / 1_000, "K"
            else:
                return str(n)
            return f"{val:.2f}".rstrip("0").rstrip(".") + suffix

        # 缓存命中率是基于 Metrics计算的。 可视化工具只是格式化它。
        def fmt_rate(rate: float | None) -> str:
            return f"{rate * 100:.2f}%" if rate is not None else "N/A"

        request_usage = None if force_totals else self._find_request_usage(event)
        if request_usage is not None:
            input_str = (
                f"↑ input {abbr(request_usage.prompt_tokens or 0)} "
                f"(total {abbr(usage.prompt_tokens or 0)})"
            )
            output_str = (
                f"↓ output {abbr(request_usage.completion_tokens or 0)} "
                f"(total {abbr(usage.completion_tokens or 0)})"
            )
            request_rate = MetricsSnapshot(
                accumulated_token_usage=request_usage
            ).cache_hit_rate
            cache_rate = (
                f"{fmt_rate(request_rate)} "
                f"(total {fmt_rate(combined_metrics.cache_hit_rate)})"
            )
            request_reasoning_tokens = request_usage.reasoning_tokens or 0
            total_reasoning_tokens = usage.reasoning_tokens or 0
            show_reasoning = request_reasoning_tokens > 0 or total_reasoning_tokens > 0
            reasoning_str = (
                f"reasoning {abbr(request_reasoning_tokens)} "
                f"(total {abbr(total_reasoning_tokens)})"
            )
        else:
            # 没有每个请求的使用可归因于此事件（没有
            # ``llm_response_id``，或类似 ACP 的路径，其中响应 ID 是每个会话）。 这里的
            # 所有数字都是累计值，所以应该标记为累计值。例如，单独的数字应该读作“每请求”
            # ，这正是#4105要解决的问题。
            #
            input_str = f"↑ input (total {abbr(usage.prompt_tokens or 0)})"
            output_str = f"↓ output (total {abbr(usage.completion_tokens or 0)})"
            cache_rate = f"(total {fmt_rate(combined_metrics.cache_hit_rate)})"
            total_reasoning_tokens = usage.reasoning_tokens or 0
            show_reasoning = total_reasoning_tokens > 0
            reasoning_str = f"reasoning (total {abbr(total_reasoning_tokens)})"

        # 成本始终是累积的：``Cost`` 条目不包含 ``response_id``（与 ``TokenUsage`` 不同
        # ），因此无法归因于每个请求的成本。
        #
        cost_str = f"{cost:.4f}" if cost > 0 else "0.00"

        # 使用固定配色方案构建
        parts: list[str] = []
        parts.append(f"[cyan]{input_str}[/cyan]")
        parts.append(f"[magenta]cache hit {cache_rate}[/magenta]")
        if show_reasoning:
            parts.append(f"[yellow] {reasoning_str}[/yellow]")
        parts.append(f"[blue]{output_str}[/blue]")
        parts.append(f"[green]$ (total {cost_str})[/green]")

        return "Tokens: " + " • ".join(parts)
