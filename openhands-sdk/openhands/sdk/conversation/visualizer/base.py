from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, final

from openhands.sdk.event.base import Event


if TYPE_CHECKING:
    from openhands.sdk.conversation.base import ConversationStateProtocol
    from openhands.sdk.conversation.conversation_stats import ConversationStats


class ConversationVisualizerBase(ABC):
    """对话可视化工具的基类。

    这个抽象基类定义了所有对话可视化工具必须实现的接口。 可视化工具可以在对话初始化之
    前创建，并将自动配置对话状态。

    典型的使用模式：
    1. 创建一个可视化工具实例：
       `viz = MyVisualizer()`
    2. 将其传递到对话：`conv = Conversation(agent, visualizer=viz)`
    3. 会话自动调用`viz.initialize(state)`附加状态

    如果不需要额外的参数，也可以传递未实例化的类
        for initialization, and Conversation will create it:
         `conv = Conversation(agent, visualizer=MyVisualizer)`
    然后对话将调用 `MyVisualizer()`，然后调用 `initialize(state)`
    """

    _state: "ConversationStateProtocol | None"

    def __init__(self):
        """初始化可视化器基础。"""
        self._state = None

    @final
    def initialize(self, state: "ConversationStateProtocol") -> None:
        """使用对话状态初始化可视化工具。

        该方法在会话状态创建后被调用，允许可视化器访问会话统计信息和其他状态信息。

        子类不应重写此方法，以确保状态已设置。

        Args:
            state: 会话状态对象
        """
        self._state = state

    @property
    def conversation_stats(self) -> "ConversationStats | None":
        """从州获取对话统计数据。"""
        return self._state.stats if self._state else None

    @abstractmethod
    def on_event(self, event: Event) -> None:
        """处理对话事件。

        对话中的每个事件都会调用此方法，并且应该实现可视化逻辑。

        Args:
            event: 可视化事件
        """
        pass

    def create_sub_visualizer(
        self,
        agent_id: str,  # noqa: ARG002
    ) -> "ConversationVisualizerBase | None":
        """在委派期间为子智能体创建可视化工具。

        重写此方法以支持多智能体委托场景中的子智能体可视化。 子可视化器将用于显示事件
        from the spawned sub-agent.

        默认情况下，返回None，这意味着子智能体将没有可视化。 支持委托的子类（如
        DelegationVisualizer）应重写此方法以创建适当的子可视化器。

        Args:
            agent_id: 正在生成的子智能体的标识符

        Returns:
            子智能体的可视化工具实例，如果不支持子智能体可视化，则为 None
        """
        return None
