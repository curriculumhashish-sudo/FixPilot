"""测试 for events_to_messages 转换操作 openhands-sdk/event/base.py."""  # type: ignore

import json
from collections.abc import Sequence
from typing import cast

import pytest

from openhands.sdk.event.base import LLMConvertibleEvent
from openhands.sdk.event.condenser import CondensationSummaryEvent
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    AgentErrorEvent,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
)
from openhands.sdk.llm import (
    ImageContent,
    Message,
    MessageToolCall,
    ReasoningItemModel,
    TextContent,
    ThinkingBlock,
)
from openhands.sdk.tool import Action, Observation


class EventsToMessagesMockAction(Action):
    """模拟对象测试操作。"""

    command: str


class EventsToMessagesMockObservation(Observation):
    """模拟对象观测结果用于测试。"""

    result: str

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


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


def create_action_event(
    thought_text: str,
    tool_name: str,
    tool_call_id: str,
    llm_response_id: str,
    action_args: dict,
) -> ActionEvent:
    """创建 ActionEvent 的帮助程序。"""
    action = EventsToMessagesMockAction(command=action_args.get("command", "test"))
    tool_call = create_tool_call(tool_call_id, tool_name, action_args)

    return ActionEvent(
        source="agent",
        thought=[TextContent(text=thought_text)],
        action=action,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_call=tool_call,
        llm_response_id=llm_response_id,
    )


class TestEventsToMessages:
    """测试用例代表 events_to_messages 功能。"""

    def test_empty_events_list(self):
        """测试空事件列表的转换。"""
        events = []
        messages = LLMConvertibleEvent.events_to_messages(events)
        assert messages == []

    def test_single_message_event(self):
        """测试单MessageEvent的转换。"""
        message_event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="Hello, how are you?")]
            ),
        )

        events = cast(list[LLMConvertibleEvent], [message_event])
        messages = LLMConvertibleEvent.events_to_messages(events)

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert len(messages[0].content) == 1
        assert isinstance(messages[0].content[0], TextContent)
        assert messages[0].content[0].text == "Hello, how are you?"

    def test_consecutive_user_message_events_are_merged(self):
        """合成用户上下文不应创建相邻的用户回合。"""
        user_message = MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="Implement the feature")]
            ),
        )
        user_context = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Relevant project context")],
            ),
        )
        assistant_message = MessageEvent(
            source="agent",
            llm_message=Message(
                role="assistant", content=[TextContent(text="I'll take a look.")]
            ),
        )

        events = cast(
            list[LLMConvertibleEvent], [user_message, user_context, assistant_message]
        )
        messages = LLMConvertibleEvent.events_to_messages(events)

        assert [message.role for message in messages] == ["user", "assistant"]
        assert [
            content.text
            for content in messages[0].content
            if isinstance(content, TextContent)
        ] == [
            "Implement the feature",
            "Relevant project context",
        ]

    def test_user_message_merge_cascades_across_three_events(self):
        """合并的消息保持普通用户轮流，因此合并是级联的。"""
        first = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="one")]),
        )
        second = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="two")]),
        )
        third = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="three")]),
        )

        events = cast(list[LLMConvertibleEvent], [first, second, third])
        messages = LLMConvertibleEvent.events_to_messages(events)

        assert [message.role for message in messages] == ["user"]
        assert [
            content.text
            for content in messages[0].content
            if isinstance(content, TextContent)
        ] == ["one", "two", "three"]

    def test_user_message_merge_preserves_mixed_content_order(self):
        """合并的内容按日志顺序、文本和图像等方式连接。"""
        text_first = MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="what is in this image?")]
            ),
        )
        image_second = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[ImageContent(image_urls=["http://example.com/a.png"])],
            ),
        )

        events = cast(list[LLMConvertibleEvent], [text_first, image_second])
        messages = LLMConvertibleEvent.events_to_messages(events)

        assert len(messages) == 1
        assert [type(content) for content in messages[0].content] == [
            TextContent,
            ImageContent,
        ]

    def test_condensation_summary_merges_with_adjacent_user_message(self):
        """摘要事件转换为普通用户消息，因此它会合并。

        上下文压缩器插入了总结，从 summary_offset == forgetting_start 处开始，而保留
        的后缀可以合法以用户消息开头，因此这种相邻关
        系是可达的，融合会抹去总结的结构边界。
        """
        summary_event = CondensationSummaryEvent(
            summary="Earlier we refactored the module."
        )
        user_after = MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="Now continue.")]
            ),
        )

        events = cast(list[LLMConvertibleEvent], [summary_event, user_after])
        messages = LLMConvertibleEvent.events_to_messages(events)

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert [
            content.text
            for content in messages[0].content
            if isinstance(content, TextContent)
        ] == ["Earlier we refactored the module.", "Now continue."]

    def test_user_messages_with_tool_call_id_not_merged(self):
        """工具结果用户消息不得合并。"""
        result = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Tool output")],
                tool_call_id="call_abc",
            ),
        )
        context = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Additional context")],
            ),
        )

        events = cast(list[LLMConvertibleEvent], [result, context])
        messages = LLMConvertibleEvent.events_to_messages(events)
        assert len(messages) == 2

    def test_user_messages_with_tool_calls_not_merged(self):
        """不得合并包含工具调用的用户消息。"""
        tool_msg = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Call this tool")],
                tool_calls=[
                    MessageToolCall(
                        id="call_1",
                        name="search",
                        arguments="{}",
                        origin="completion",
                    )
                ],
            ),
        )
        plain = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Plain message")],
            ),
        )

        events = cast(list[LLMConvertibleEvent], [tool_msg, plain])
        messages = LLMConvertibleEvent.events_to_messages(events)
        assert len(messages) == 2

    def test_user_messages_with_name_not_merged(self):
        """命名用户消息不得合并。"""
        named = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Named output")],
                name="search_results",
            ),
        )
        plain = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Plain message")],
            ),
        )

        events = cast(list[LLMConvertibleEvent], [named, plain])
        messages = LLMConvertibleEvent.events_to_messages(events)
        assert len(messages) == 2

    def test_mixed_role_messages_not_merged(self):
        """具有不同角色的消息不得合并。"""
        assistant_msg = MessageEvent(
            source="agent",
            llm_message=Message(
                role="assistant",
                content=[TextContent(text="Assistant reply")],
            ),
        )
        user_msg = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="User message")],
            ),
        )

        events = cast(list[LLMConvertibleEvent], [assistant_msg, user_msg])
        messages = LLMConvertibleEvent.events_to_messages(events)
        assert len(messages) == 2
        assert messages[0].role == "assistant"
        assert messages[1].role == "user"

    def test_single_action_event(self):
        """测试单ActionEvent的转换。"""
        action_event = create_action_event(
            thought_text="I need to run a command",
            tool_name="terminal",
            tool_call_id="call_123",
            llm_response_id="response_1",
            action_args={"command": "ls -la"},
        )

        events = cast(list[LLMConvertibleEvent], [action_event])
        messages = LLMConvertibleEvent.events_to_messages(events)

        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert len(messages[0].content) == 1
        assert isinstance(messages[0].content[0], TextContent)
        assert messages[0].content[0].text == "I need to run a command"
        assert messages[0].tool_calls is not None
        assert len(messages[0].tool_calls) == 1
        assert messages[0].tool_calls[0].id == "call_123"
        assert messages[0].tool_calls[0].name == "terminal"

    def test_parallel_function_calling_same_response_id(self):
        """使用具有相同 ID 的多个 ActionEvents 测试并行函数调用。

        这模拟了LiteLLM文档中的场景，其中模型在并行下执行多个函数调用(e.g.，获取多个
        城市的天气预报)。
        """
        # 使用相同的 llm_response_id 创建多个 ActionEvents 第一个事件有思想，其他事件应
        # 该有空的思想
        #
        action1 = create_action_event(
            thought_text="I need to get weather for multiple cities",
            tool_name="get_current_weather",
            tool_call_id="call_SF",
            llm_response_id="response_parallel",
            action_args={"location": "San Francisco", "unit": "celsius"},
        )

        action2 = ActionEvent(
            source="agent",
            thought=[],  # 对并行调用中后续操作的空想
            action=EventsToMessagesMockAction(command="test"),
            tool_name="get_current_weather",
            tool_call_id="call_Tokyo",
            tool_call=create_tool_call(
                "call_Tokyo",
                "get_current_weather",
                {"location": "Tokyo", "unit": "celsius"},
            ),
            llm_response_id="response_parallel",
        )

        action3 = ActionEvent(
            source="agent",
            thought=[],  # 对并行调用中后续操作的空想
            action=EventsToMessagesMockAction(command="test"),
            tool_name="get_current_weather",
            tool_call_id="call_Paris",
            tool_call=create_tool_call(
                "call_Paris",
                "get_current_weather",
                {"location": "Paris", "unit": "celsius"},
            ),
            llm_response_id="response_parallel",
        )

        events = cast(list[LLMConvertibleEvent], [action1, action2, action3])
        messages = LLMConvertibleEvent.events_to_messages(events)

        # 应与多个 tool_calls 合并为单个助理消息
        assert len(messages) == 1
        assert messages[0].role == "assistant"

        # 内容应该来自第一个事件的想法
        assert len(messages[0].content) == 1
        assert isinstance(messages[0].content[0], TextContent)
        assert (
            messages[0].content[0].text == "I need to get weather for multiple cities"
        )

        # 应该具备全部三个工具调用
        tool_calls = messages[0].tool_calls
        assert tool_calls is not None
        assert len(tool_calls) == 3

        # 验证工具调用详细信息确切的顺序，而不是成员身份：批次内的顺序是日志顺序。
        #
        assert [tc.id for tc in tool_calls] == ["call_SF", "call_Tokyo", "call_Paris"]

        # 全部应该是天气函数调用
        for tool_call in tool_calls:
            assert tool_call.name == "get_current_weather"

    def test_parallel_batch_preserves_first_event_reasoning(self):
        """组合消息保留第一个事件的推理状态。

        ThinkingBlock的自身文档字符串要求这些块必须保留并传递给API用于工具使用场景——
        因此，批量消息必须像单例一样精确地携带它们。
        """
        first = ActionEvent(
            source="agent",
            thought=[TextContent(text="batching two calls")],
            reasoning_content="step-by-step reasoning",
            thinking_blocks=[ThinkingBlock(thinking="let me think", signature="sig-1")],
            action=EventsToMessagesMockAction(command="one"),
            tool_name="terminal",
            tool_call_id="call_1",
            tool_call=create_tool_call("call_1", "terminal", {"command": "one"}),
            llm_response_id="response_reasoning",
        )
        second = ActionEvent(
            source="agent",
            thought=[],
            action=EventsToMessagesMockAction(command="two"),
            tool_name="terminal",
            tool_call_id="call_2",
            tool_call=create_tool_call("call_2", "terminal", {"command": "two"}),
            llm_response_id="response_reasoning",
        )

        events = [first, second]
        messages = LLMConvertibleEvent.events_to_messages(events)  # type: ignore

        assert len(messages) == 1
        combined = messages[0]
        assert combined.reasoning_content == "step-by-step reasoning"
        assert len(combined.thinking_blocks) == 1
        assert combined.thinking_blocks[0].thinking == "let me think"  # type: ignore

    def test_parallel_batch_preserves_responses_reasoning_item(self):
        """单例保留其响应推理项； 也必须有一批。"""
        first = ActionEvent(
            source="agent",
            thought=[TextContent(text="batching two calls")],
            responses_reasoning_item=ReasoningItemModel(
                id="rs_1", summary=["reasoned about the batch"]
            ),
            action=EventsToMessagesMockAction(command="one"),
            tool_name="terminal",
            tool_call_id="call_1",
            tool_call=create_tool_call("call_1", "terminal", {"command": "one"}),
            llm_response_id="response_reasoning_item",
        )
        second = ActionEvent(
            source="agent",
            thought=[],
            action=EventsToMessagesMockAction(command="two"),
            tool_name="terminal",
            tool_call_id="call_2",
            tool_call=create_tool_call("call_2", "terminal", {"command": "two"}),
            llm_response_id="response_reasoning_item",
        )

        events = [first, second]
        messages = LLMConvertibleEvent.events_to_messages(events)  # type: ignore

        assert len(messages) == 1
        combined = messages[0]
        # 整个项目平等，而不仅仅是 id — 未来字段损失在这里失败。
        assert combined.responses_reasoning_item == ReasoningItemModel(
            id="rs_1", summary=["reasoned about the batch"]
        )

    def test_multiple_separate_action_events(self):
        """使用不同的 response_ids 测试多个 ActionEvents（单独的调用）。"""
        action1 = create_action_event(
            thought_text="First command",
            tool_name="terminal",
            tool_call_id="call_1",
            llm_response_id="response_1",
            action_args={"command": "ls"},
        )

        action2 = create_action_event(
            thought_text="Second command",
            tool_name="terminal",
            tool_call_id="call_2",
            llm_response_id="response_2",
            action_args={"command": "pwd"},
        )

        events = [action1, action2]
        messages = LLMConvertibleEvent.events_to_messages(events)  # type: ignore

        # 应为不同的响应 ID 创建单独的消息
        assert len(messages) == 2

        assert messages[0].role == "assistant"
        assert messages[0].content[0].text == "First command"  # type: ignore
        assert messages[0].tool_calls[0].id == "call_1"  # type: ignore

        assert messages[1].role == "assistant"
        assert messages[1].content[0].text == "Second command"  # type: ignore
        assert messages[1].tool_calls[0].id == "call_2"  # type: ignore

    def test_mixed_event_types(self):
        """按顺序测试混合事件类型的转换。"""
        # 系统提示词
        system_event = SystemPromptEvent(
            system_prompt=TextContent(text="You are a helpful assistant."), tools=[]
        )

        # 用户留言
        user_message = MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="What's the weather like?")]
            ),
        )

        # 动作事件
        action_event = create_action_event(
            thought_text="I'll check the weather",
            tool_name="get_weather",
            tool_call_id="call_weather",
            llm_response_id="response_weather",
            action_args={"location": "current"},
        )

        # 观测结果活动
        observation_event = ObservationEvent(
            source="environment",
            observation=EventsToMessagesMockObservation(result="Sunny, 72°F"),
            action_id="action_123",
            tool_name="get_weather",
            tool_call_id="call_weather",
        )

        events = [system_event, user_message, action_event, observation_event]
        messages = LLMConvertibleEvent.events_to_messages(events)

        assert len(messages) == 4

        # 系统消息
        assert messages[0].role == "system"
        assert messages[0].content[0].text == "You are a helpful assistant."  # type: ignore

        # 用户留言
        assert messages[1].role == "user"
        assert messages[1].content[0].text == "What's the weather like?"  # type: ignore

        # 助理消息工具调用
        assert messages[2].role == "assistant"
        assert messages[2].content[0].text == "I'll check the weather"  # type: ignore
        assert messages[2].tool_calls is not None
        assert messages[2].tool_calls[0].id == "call_weather"  # type: ignore

        # 工具响应
        assert messages[3].role == "tool"
        assert messages[3].content[0].text == "Sunny, 72°F"  # type: ignore
        assert messages[3].tool_call_id == "call_weather"
        assert messages[3].name == "get_weather"

    def test_agent_error_event(self):
        """测试 AgentErrorEvent 的转换。"""
        error_event = AgentErrorEvent(
            error="Command failed with exit code 1",
            tool_call_id="call_err",
            tool_name="terminal",
        )

        events = [error_event]
        messages = LLMConvertibleEvent.events_to_messages(events)  # type: ignore

        assert len(messages) == 1
        assert messages[0].role == "tool"
        assert messages[0].content[0].text == "Command failed with exit code 1"  # type: ignore

    def test_complex_parallel_and_sequential_mix(self):
        """使用并行和顺序函数调用测试复杂场景。"""
        # 第一：用户留言
        user_msg = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[
                    TextContent(text="Get weather for SF and NYC, then list files")
                ],
            ),
        )

        # 第二：并行天气调用（同response_id）
        weather_sf = create_action_event(
            thought_text="I'll get weather for both cities in parallel",
            tool_name="get_weather",
            tool_call_id="call_sf_weather",
            llm_response_id="parallel_weather",
            action_args={"location": "San Francisco"},
        )

        weather_nyc = ActionEvent(
            source="agent",
            thought=[],  # 并行调用时为空
            action=EventsToMessagesMockAction(command="test"),
            tool_name="get_weather",
            tool_call_id="call_nyc_weather",
            tool_call=create_tool_call(
                "call_nyc_weather", "get_weather", {"location": "New York"}
            ),
            llm_response_id="parallel_weather",
        )

        # 第三：天气观测结果
        obs_sf = ObservationEvent(
            source="environment",
            observation=EventsToMessagesMockObservation(result="SF: Sunny, 65°F"),
            action_id="action_sf",
            tool_name="get_weather",
            tool_call_id="call_sf_weather",
        )

        obs_nyc = ObservationEvent(
            source="environment",
            observation=EventsToMessagesMockObservation(result="NYC: Cloudy, 45°F"),
            action_id="action_nyc",
            tool_name="get_weather",
            tool_call_id="call_nyc_weather",
        )

        # 第四：单独文件列表调用（不同response_id）
        list_files = create_action_event(
            thought_text="Now I'll list the files",
            tool_name="terminal",
            tool_call_id="call_ls",
            llm_response_id="list_files_response",
            action_args={"command": "ls -la"},
        )

        events = [user_msg, weather_sf, weather_nyc, obs_sf, obs_nyc, list_files]
        messages = LLMConvertibleEvent.events_to_messages(events)

        assert len(messages) == 5

        # 用户留言
        assert messages[0].role == "user"

        # 联合并行天气呼叫
        assert messages[1].role == "assistant"
        assert (
            messages[1].content[0].text  # type: ignore
            == "I'll get weather for both cities in parallel"
        )
        assert len(messages[1].tool_calls) == 2  # type: ignore

        # 天气观测结果
        assert messages[2].role == "tool"
        assert messages[2].tool_call_id == "call_sf_weather"
        assert messages[3].role == "tool"
        assert messages[3].tool_call_id == "call_nyc_weather"

        # 单独的文件列表调用
        assert messages[4].role == "assistant"
        assert messages[4].content[0].text == "Now I'll list the files"  # type: ignore
        assert len(messages[4].tool_calls) == 1  # type: ignore
        assert messages[4].tool_calls[0].id == "call_ls"  # type: ignore

    def test_assertion_error_for_non_empty_thought_in_parallel_calls(self):
        """在后续并行调用中测试非空思想的断言错误。"""
        action1 = create_action_event(
            thought_text="First thought",
            tool_name="get_weather",
            tool_call_id="call_1",
            llm_response_id="same_response",
            action_args={"location": "SF"},
        )

        # 这应该会导致断言错误 - 后续调用中的非空思想
        action2 = ActionEvent(
            source="agent",
            thought=[TextContent(text="This should not be here!")],  # 非空念
            action=EventsToMessagesMockAction(command="test"),
            tool_name="get_weather",
            tool_call_id="call_2",
            tool_call=create_tool_call("call_2", "get_weather", {"location": "NYC"}),
            llm_response_id="same_response",
        )

        events = [action1, action2]

        with pytest.raises(
            AssertionError,
            match="Expected empty thought for multi-action events after the first one",
        ):
            LLMConvertibleEvent.events_to_messages(events)  # type: ignore

    def test_action_event_with_none_action_round_trip_and_observation_match(self):
        """使用 action=None 往返和观测结果匹配测试 ActionEvent。"""
        thought = [TextContent(text="thinking...")]
        tc = create_tool_call("call_ne", "missing_tool", {"x": 1})
        action_event = ActionEvent(
            source="agent",
            thought=thought,
            tool_call=tc,
            tool_name=tc.name,
            tool_call_id=tc.id,
            llm_response_id="resp_events_1",
            action=None,
        )

        # 转换为消息并确保助理消息具有单个 tool_call
        messages = LLMConvertibleEvent.events_to_messages([action_event])
        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].tool_calls is not None and len(messages[0].tool_calls) == 1
        assert messages[0].tool_calls[0].id == "call_ne"
        assert messages[0].tool_calls[0].name == "missing_tool"

        # 模拟带有相同 tool_call_id 的 AgentErrorEvent
        err = AgentErrorEvent(
            error="not found",
            tool_call_id="call_ne",
            tool_name="missing_tool",
        )

        msgs = LLMConvertibleEvent.events_to_messages([action_event, err])
        # 应该产生两条消息：assistant 工具调用 + tool error
        assert len(msgs) == 2
        assert msgs[0].role == "assistant"
        assert msgs[1].role == "tool"
        assert msgs[1].tool_call_id == "call_ne"
