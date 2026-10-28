"""测试可配置的卡住检测阈值。"""

from pydantic import SecretStr

from openhands.sdk import Agent, LocalConversation
from openhands.sdk.event import ActionEvent, ObservationEvent
from openhands.sdk.llm import LLM, MessageToolCall, TextContent
from openhands.tools.terminal.definition import (
    TerminalAction,
    TerminalObservation,
)


def test_custom_action_observation_threshold():
    """测试自定义阈值对于 action-观测结果循环是否正常工作。"""
    # 创建门槛较高的对话
    conv = LocalConversation(
        Agent(llm=LLM(model="gpt-4o-mini", api_key=SecretStr("test"))),
        workspace="/tmp",
        stuck_detection=True,
        stuck_detection_thresholds={"action_observation": 6},
    )

    # 先添加用户留言
    conv.send_message("start")

    # 创建相同的动作-观测结果对
    def create_action_obs():
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run ls command")],
            action=TerminalAction(command="ls"),
            tool_name="execute_bash",
            tool_call_id="call_1",
            tool_call=MessageToolCall(
                id="call_1",
                name="execute_bash",
                arguments='{"command": "ls"}',
                origin="completion",
            ),
            llm_response_id="response_1",
        )
        observation = ObservationEvent(
            source="environment",
            observation=TerminalObservation(
                content=[TextContent(text="file1.txt")], command="ls", exit_code=0
            ),
            action_id=action.id,
            tool_name="execute_bash",
            tool_call_id="call_1",
        )
        return action, observation

    # 添加 4 对（将触发默认阈值 4）。 通过真正的阻塞点发射，因此 HEAD 前进，就像在实时运
    # 行中一样。
    #
    for _ in range(4):
        action, observation = create_action_obs()
        with conv._state:
            conv._state.append_event(action)
            conv._state.append_event(observation)

    # 不应该被阈值=6 困住吗
    assert conv._stuck_detector is not None
    assert not conv._stuck_detector.is_stuck()

    # 再添加 2 对以达到阈值 6
    for _ in range(2):
        action, observation = create_action_obs()
        with conv._state:
            conv._state.append_event(action)
            conv._state.append_event(observation)

    # 现在应该被卡住了
    assert conv._stuck_detector.is_stuck()


def test_mixed_custom_thresholds():
    """测试一次设置多个自定义阈值。"""
    conv = LocalConversation(
        Agent(llm=LLM(model="gpt-4o-mini", api_key=SecretStr("test"))),
        workspace="/tmp",
        stuck_detection=True,
        stuck_detection_thresholds={
            "action_observation": 8,
            "action_error": 6,
            "monologue": 10,
        },
    )

    assert conv._stuck_detector is not None
    assert conv._stuck_detector.action_observation_threshold == 8
    assert conv._stuck_detector.action_error_threshold == 6
    assert conv._stuck_detector.monologue_threshold == 10
    # alternating_pattern 应使用默认值
    assert conv._stuck_detector.alternating_pattern_threshold == 6
