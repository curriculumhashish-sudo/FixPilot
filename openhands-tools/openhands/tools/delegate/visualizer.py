"""
特定于委派的可视化工具，显示多智能体委派的发送者/接收者信息。
"""

from rich.console import Group

from openhands.sdk.conversation.visualizer.default import (
    _ACTION_COLOR,
    _OBSERVATION_COLOR,
    _SYSTEM_COLOR,
    DefaultConversationVisualizer,
    build_event_block,
)
from openhands.sdk.event import (
    ActionEvent,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
)
from openhands.sdk.event.base import Event


class DelegationVisualizer(DefaultConversationVisualizer):
    """
    智能体委托的自定义可视化工具，显示详细的发送者/接收者信息。

    此可视化工具扩展了默认可视化工具，以在委托场景期间提供更清晰的多智能体对话可视化
    。 它显示：
    - 每条消息的发送者（e.g.、“委托人”、“住宿专家”）
    - 预期收件人是谁
    - 智能体之间清晰的定向流动

    标题示例：
    - 《代表给住宿专家的留言》
    - 《给委托人的住宿专家留言》
    - “用户给委托人的消息”
    """

    _name: str | None

    def __init__(
        self,
        name: str | None = None,
        highlight_regex: dict[str, str] | None = None,
        skip_user_messages: bool = False,
    ):
        """初始化委托可视化工具。

        Args:
            name: 智能体在委托上下文的面板标题中显示的名称。
            highlight_regex: 将正则表达式模式映射到丰富颜色样式的字典
                           用于在可视化工具中突出显示关键字。
            skip_user_messages: 如果为 True，则跳过显示用户消息。
        """
        super().__init__(
            highlight_regex=highlight_regex,
            skip_user_messages=skip_user_messages,
        )
        self._name = name

    def create_sub_visualizer(self, agent_id: str) -> "DelegationVisualizer":
        """在委派期间为子智能体创建可视化工具。

        为子智能体创建一个新的 DelegationVisualizer 实例，其配置与父可视化工具相同。

        Args:
            agent_id: 正在生成的子智能体的标识符

        Returns:
            为子智能体配置的新 DelegationVisualizer
        """
        return DelegationVisualizer(
            name=agent_id,
            highlight_regex=self._highlight_patterns,
            skip_user_messages=self._skip_user_messages,
        )

    @staticmethod
    def _format_agent_name(name: str) -> str:
        """
        将 snake_case 或 camelCase 智能体名称转换为标题大小写以供显示。

        Args:
            name: 智能体名称在 snake_case 中（e.g.、“lodging_expert”）或
                  camelCase (e.g., "MainAgent") 或已格式化 (e.g., "Main 智能体")

        Returns:
            首字母大写格式的名称（e.g.、“住宿专家”或“主要智能体”）

        Examples:
            >>> DelegationVisualizer._format_agent_name("lodging_expert")
            “住宿专家”
            >>> DelegationVisualizer._format_agent_name("MainAgent")
            '主智能体'
            >>> DelegationVisualizer._format_agent_name("main_delegator")
            “主要代表”
            >>> DelegationVisualizer._format_agent_name("Main Agent")
            '主智能体'
        """
        # 如果已经有空格，则假设它已经格式化
        if " " in name:
            return name

        # 通过用空格替换下划线来处理 snake_case
        if "_" in name:
            return name.replace("_", " ").title()

        # 通过在大写字母前插入空格来处理 camelCase/PascalCase
        import re

        # 在每个大写字母前插入空格（第一个字母除外）
        spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", name)
        return spaced.title()

    def _create_event_block(self, event: Event) -> Group | None:
        """
        覆盖事件块创建以将智能体名称添加到标题中。

        对于系统提示词、操作和观测结果，在前面添加智能体名称（e.g.、“委托人智能体系统
        提示词”、“委托人智能体操作”、“住宿专家智能体观测结果”）。 对于消息，
        委托给专门的消息处理程序。

        Args:
            event: 可视化事件

        Returns:
            具有智能体特定标题的 Rich Group，如果可视化失败则为 None
        """
        # 对于消息事件，请使用我们的专用处理程序，同时保留父可视化工具基于源的用户消息过
        # 滤。
        #
        if isinstance(event, MessageEvent):
            if self._skip_user_messages and event.source == "user":
                return None
            return self._create_message_event_block(event)

        # 对于系统提示词、操作和观测结果，将智能体名称添加到标题中
        if isinstance(event, (SystemPromptEvent, ActionEvent, ObservationEvent)):
            content = event.visualize
            if not content.plain.strip():
                return None

            # 如果已配置，则应用突出显示
            if self._highlight_patterns:
                content = self._apply_highlighting(content)

            agent_name = self._format_agent_name(self._name) if self._name else "Agent"

            if isinstance(event, SystemPromptEvent):
                title = f"{agent_name} Agent System Prompt"
                return build_event_block(
                    content=content,
                    title=title,
                    title_color=_SYSTEM_COLOR,
                )
            elif isinstance(event, ActionEvent):
                # 检查操作是否为None（不可执行）
                if event.action is None:
                    title = f"{agent_name} Agent Action (Not Executed)"
                else:
                    title = f"{agent_name} Agent Action"
                return build_event_block(
                    content=content,
                    title=title,
                    title_color=_ACTION_COLOR,
                    # 并行工具调用批处理的同级会回退到仅总计，因此不会重复共享的每个请求
                    # 使用情况。
                    #
                    subtitle=self._format_metrics_subtitle(
                        event, force_totals=not self._claim_batch_primary(event)
                    ),
                )
            else:  # ObservationEvent
                title = f"{agent_name} Agent Observation"
                return build_event_block(
                    content=content,
                    title=title,
                    title_color=_OBSERVATION_COLOR,
                )

        # 对于所有其他事件类型，请使用父实现
        return super()._create_event_block(event)

    def _create_message_event_block(self, event: MessageEvent) -> Group | None:
        """
        使用特定于委托的发送者/接收者信息为消息事件创建块。

        对于人工或委托消息（source="user"）：
        - 如果设置了发件人：“[发件人] 智能体消息至[智能体]智能体”
        - Otherwise: “发送给 [智能体]智能体的用户消息”

        对于框架消息（source =“environment”或source =“hook”）：
        - “从[来源]到[智能体]智能体的消息”

        对于智能体条消息（来源 =“智能体”）：
        - 从事件历史记录中获取收件人（最后的用户消息发件人）
        - 如果收件人找到：“[智能体] 智能体消息给 [收件人] 智能体”
        - Otherwise: “[智能体]智能体给用户的消息”

        Args:
            event: 要可视化的消息事件

        Returns:
            具有委托感知标题的 Rich Group，如果可视化失败则为 None
        """
        content = event.visualize
        if not content.plain.strip():
            return None

        assert event.llm_message is not None

        # 事件来源代表作者身份； LLM 角色仅控制有线协议，并且可能有意为框架反馈而有所不
        # 同。
        #
        if event.source == "user":
            role_color = "gold3"
        elif event.source == "agent":
            role_color = "blue"
        else:
            role_color = _SYSTEM_COLOR

        # 使用授权的发件人/收件人信息构建标题
        agent_name = self._format_agent_name(self._name) if self._name else "Agent"

        if event.source == "user":
            if event.sender:
                # 来自另一个智能体的消息（通过委托）
                sender_display = self._format_agent_name(event.sender)
                title = f"{sender_display} Agent Message to {agent_name} Agent"
            else:
                # 普通用户留言
                title = f"User Message to {agent_name} Agent"
        elif event.source in ("environment", "hook"):
            source_display = event.source.title()
            title = f"Message from {source_display} to {agent_name} Agent"
        else:
            # 对于智能体条消息，从上一条用户消息中派生收件人
            recipient = None
            if self._state:
                for evt in reversed(self._state.events):
                    if isinstance(evt, MessageEvent) and evt.source == "user":
                        recipient = evt.sender
                        break

            if recipient:
                # 智能体回复另一个智能体
                recipient_display = self._format_agent_name(recipient)
                title = f"{agent_name} Agent Message to {recipient_display} Agent"
            else:
                # 智能体回复用户
                title = f"Message from {agent_name} Agent to User"

        return build_event_block(
            content=content,
            title=title,
            title_color=role_color,
            subtitle=self._format_metrics_subtitle(event),
        )
