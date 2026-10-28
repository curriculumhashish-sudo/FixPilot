from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.conversation.types import StuckDetectionThresholds
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    CondensationSummaryEvent,
    Event,
    MessageEvent,
    ObservationBaseEvent,
    ObservationEvent,
)
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


# 扫描滞留检测的最近最大事件数。 该窗口应足够大以捕获重复模式（4 次重复 × 每个周期 2 个
# 事件 = 最少 8 个事件，加上用户消息的缓冲区）
#
MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION: int = 20


class StuckDetector:
    """检测智能体何时陷入重复或无效模式。

    该检测器分析对话历史记录以识别各种卡住模式：
    1. 重复动作-观测结果个周期
    2. 重复动作-错误循环
    3. 智能体独白（无需用户输入的重复消息）
    4. 重复交替动作-观测结果模式
    5. 上下文窗口指示内存问题的错误
    """

    state: ConversationState
    thresholds: StuckDetectionThresholds

    def __init__(
        self,
        state: ConversationState,
        thresholds: StuckDetectionThresholds | None = None,
    ):
        self.state = state
        self.thresholds = thresholds or StuckDetectionThresholds()
        # AgentErrorEvent 的 ID 已经被微移，因此冻结了条纹 (e.g. 不添加新操作的空/仅推理
        # 响应）不会在每次迭代时重新发出相同的推动。
        #
        self._last_nudged_error_event_id: str | None = None

    @property
    def action_observation_threshold(self) -> int:
        return self.thresholds.action_observation

    @property
    def action_error_threshold(self) -> int:
        return self.thresholds.action_error

    @property
    def monologue_threshold(self) -> int:
        return self.thresholds.monologue

    @property
    def alternating_pattern_threshold(self) -> int:
        return self.thresholds.alternating_pattern

    def _events_since_last_user_message(self) -> list[Event]:
        """最后一条用户消息（如果有）之后，扫描窗口中的事件。

        窗口化而不是完整历史记录，以避免具体化大型文件支持的事件日志。
        """
        events = self.state.active_branch(limit=MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION)

        last_user_msg_index = next(
            (
                i
                for i in reversed(range(len(events)))
                if isinstance(events[i], MessageEvent) and events[i].source == "user"
            ),
            -1,  # 如果未找到用户消息，则默认为 -1
        )
        if last_user_msg_index != -1:
            events = events[last_user_msg_index + 1 :]
        return events

    def _collect_actions_and_observations(
        self, events: list[Event], max_needed: int
    ) -> tuple[list[Event], list[Event]]:
        """最后的 ``max_needed`` 操作和观测结果，最近的在最前面。"""
        last_actions: list[Event] = []
        last_observations: list[Event] = []
        for event in reversed(events):
            if isinstance(event, ActionEvent) and len(last_actions) < max_needed:
                last_actions.append(event)
            elif (
                isinstance(event, ObservationBaseEvent)
                and len(last_observations) < max_needed
            ):
                last_observations.append(event)
            if len(last_actions) >= max_needed and len(last_observations) >= max_needed:
                break
        return last_actions, last_observations

    def is_stuck(self) -> bool:
        """检查智能体当前是否卡住。"""
        events = self._events_since_last_user_message()

        # 确定所需的最少事件
        min_threshold = min(
            self.action_observation_threshold,
            self.action_error_threshold,
            self.monologue_threshold,
        )
        if len(events) < min_threshold:
            return False

        logger.debug(f"Checking for stuck patterns in {len(events)} events")
        logger.debug(
            f"Events after last user message: {[type(e).__name__ for e in events]}"
        )

        # action_error 需要额外一对来区分新的连胜和已经持续过去的连胜（参见
        # get_action_error_nudge）
        #
        max_needed = max(
            self.action_observation_threshold, self.action_error_threshold + 1
        )
        last_actions, last_observations = self._collect_actions_and_observations(
            events, max_needed
        )

        # 检查所有卡住模式场景 1：相同的操作，相同的观测结果
        #
        if self._is_stuck_repeating_action_observation(last_actions, last_observations):
            return True

        # 场景 2：相同的操作，错误
        if self._is_stuck_repeating_action_error(last_actions, last_observations):
            return True

        # 场景3：独白
        if self._is_stuck_monologue(events):
            return True

        # 场景 4：动作，观测结果交替模式
        if len(events) >= self.alternating_pattern_threshold:
            if self._is_stuck_alternating_action_observation(events):
                return True

        # 场景 5：上下文窗口错误循环
        if len(events) >= 10:
            if self._is_stuck_context_window_error(events):
                return True

        return False

    def _is_stuck_repeating_action_observation(
        self, last_actions: list[Event], last_observations: list[Event]
    ) -> bool:
        # 场景 1：相同的操作，相同的观测结果
        threshold = self.action_observation_threshold

        # 检查相同动作-观测结果对的循环
        if len(last_actions) >= threshold and len(last_observations) >= threshold:
            logger.debug(
                f"Found {len(last_actions)} actions and "
                f"{len(last_observations)} observations, checking for equality"
            )
            actions_equal = all(
                self._event_eq(last_actions[0], action)
                for action in last_actions[:threshold]
            )
            observations_equal = all(
                self._event_eq(last_observations[0], observation)
                for observation in last_observations[:threshold]
            )
            logger.debug(
                f"Actions equal: {actions_equal}, "
                f"Observations equal: {observations_equal}"
            )

            if actions_equal and observations_equal:
                logger.warning("Action, Observation loop detected")
                return True
        else:
            logger.debug(
                f"Not enough actions/observations: {len(last_actions)} actions,"
                f" {len(last_observations)} observations"
            )

        return False

    def _action_error_streak(
        self, last_actions: list[Event], last_observations: list[Event]
    ) -> int:
        """一个动作的尾随运行长度反复出错。"""
        if not last_actions or not last_observations:
            return 0
        reference = last_actions[0]
        streak = 0
        for action, observation in zip(last_actions, last_observations):
            if not self._event_eq(reference, action):
                break
            if not isinstance(observation, AgentErrorEvent):
                break
            streak += 1
        return streak

    def _is_stuck_repeating_action_error(
        self, last_actions: list[Event], last_observations: list[Event]
    ) -> bool:
        # 场景 2：相同的操作，错误 — 重复一次超过阈值
        threshold = self.action_error_threshold
        if self._action_error_streak(last_actions, last_observations) > threshold:
            logger.warning("Action, Error loop detected")
            return True
        return False

    def get_action_error_nudge(self) -> str | None:
        """一旦操作错误连续第一次达到阈值，就微移文本。

        每个条纹微移一次：如果条纹在同一错误事件上仍被冻结 (e.g. 空的/仅推理的响应没
        有添加新的操作）我们已经推动了它，所以我们不会重新启动。
        """
        events = self._events_since_last_user_message()
        threshold = self.action_error_threshold
        last_actions, last_observations = self._collect_actions_and_observations(
            events, threshold + 1
        )
        if self._action_error_streak(last_actions, last_observations) != threshold:
            return None

        action = last_actions[0]
        error = last_observations[0]
        assert isinstance(action, ActionEvent)
        assert isinstance(error, AgentErrorEvent)

        if error.id == self._last_nudged_error_event_id:
            return None
        self._last_nudged_error_event_id = error.id

        return (
            f"You've called `{action.tool_name}` with the same arguments "
            f"{threshold} times in a row and gotten the same error each "
            f"time: {error.error}. Repeating the exact same call again "
            "will not work — review the error message and either correct "
            "the arguments or try a different approach."
        )

    def _is_stuck_monologue(self, events: list[Event]) -> bool:
        # 3. 检查重复的MessageActions，源为AGENT，看看智能体是否在进行一段老套的独白，重
        # 复讲述同样的事情
        #
        threshold = self.monologue_threshold
        if len(events) < threshold:
            return False

        # 在没有用户中断的情况下查找 N 个连续的智能体消息
        agent_message_count = 0

        for event in reversed(events):
            if isinstance(event, MessageEvent):
                if event.source == "agent":
                    agent_message_count += 1
                elif event.source == "user":
                    break  # 用户被打断，而不是独白
            elif isinstance(event, CondensationSummaryEvent):
                # 上下文压缩事件不会打破独白模式
                continue
            else:
                # 其他事件（行动/观察）不算独白
                break

        return agent_message_count >= threshold

    def _is_stuck_alternating_action_observation(self, events: list[Event]) -> bool:
        # 场景 4：交替动作-观测结果循环
        threshold = self.alternating_pattern_threshold

        last_actions: list[Event] = []
        last_observations: list[Event] = []

        # 收集最近的 N 个动作和 N观测结果
        for event in reversed(events):
            if isinstance(event, ActionEvent) and len(last_actions) < threshold:
                last_actions.append(event)
            elif (
                isinstance(event, (ObservationEvent, AgentErrorEvent))
                and len(last_observations) < threshold
            ):
                last_observations.append(event)

            if len(last_actions) == threshold and len(last_observations) == threshold:
                break

        if len(last_actions) == threshold and len(last_observations) == threshold:
            # 检查交替模式：[A, B, A, B, A, B]，其中偶数/奇数匹配
            actions_equal = all(
                self._event_eq(last_actions[i], last_actions[i + 2])
                for i in range(threshold - 2)
            )
            observations_equal = all(
                self._event_eq(last_observations[i], last_observations[i + 2])
                for i in range(threshold - 2)
            )

            if actions_equal and observations_equal:
                logger.warning("Alternating Action, Observation loop detected")
                return True

        return False

    def _is_stuck_context_window_error(self, _events: list[Event]) -> bool:
        """检测我们是否陷入上下文窗口错误的循环中。

        当我们反复出现上下文窗口错误并尝试修剪，但修剪不起作用，导致我们出现更多上下
        文窗口错误时，就会发生这种情况。 该模式是重复
        AgentCondensationObservation 个事件，它们之间没有任何其他事件。
        """
        # TODO：被 https://github.com/OpenHands/agent-sdk/issues/282 阻止
        return False

    def _event_eq(self, event1: Event, event2: Event) -> bool:
        """
        比较两个事件的等价性，忽略无关细节如 id 和指标。
        """
        # 必须是同一类型
        if type(event1) is not type(event2):
            return False

        # 对于ActionEvents，比较动作内容，忽略ID
        if isinstance(event1, ActionEvent) and isinstance(event2, ActionEvent):
            return (
                event1.source == event2.source
                and event1.thought == event2.thought
                and event1.action == event2.action
                and event1.tool_name == event2.tool_name
                # 忽略 tool_call_id、llm_response_id、action_id，因为它们不同
            )

        # 对于 ObservationEvents，比较观测结果内容，忽略 ID
        if isinstance(event1, ObservationEvent) and isinstance(
            event2, ObservationEvent
        ):
            return (
                event1.source == event2.source
                and event1.observation == event2.observation
                and event1.tool_name == event2.tool_name
                # 忽略 action_id、tool_call_id，因为它们不同
            )

        # 对于AgentErrorEvents，比较错误内容
        if isinstance(event1, AgentErrorEvent) and isinstance(event2, AgentErrorEvent):
            return (
                event1.source == event2.source and event1.error == event2.error
                # 忽略 action_id，因为它有所不同
            )

        # 对于MessageEvents，比较消息内容
        if isinstance(event1, MessageEvent) and isinstance(event2, MessageEvent):
            return (
                event1.source == event2.source
                and event1.llm_message == event2.llm_message
            )

        # 默认回退方案
        return event1 == event2
