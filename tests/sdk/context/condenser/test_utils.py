from typing import cast
from unittest.mock import MagicMock

import pytest

from openhands.sdk.context.condenser.utils import (
    get_shortest_prefix_above_token_count,
    get_suffix_length_for_token_reduction,
    get_total_token_count,
)
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.event.llm_convertible.system import SystemPromptEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool import ToolDefinition
from openhands.sdk.tool.builtins.finish import FinishTool


def message_event(content: str) -> MessageEvent:
    """用于创建 MessageEvent 进行测试的辅助函数。"""
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


@pytest.fixture
def mock_llm() -> LLM:
    """创建具有 token 计数功能的模拟对象 LLM。"""
    mock_llm = MagicMock(spec=LLM)
    mock_llm.model = "test-model"

    # 模拟对象 get_token_count 根据消息内容长度返回可预测的值
    def mock_token_count(messages, **_kwargs):
        # 简单启发式：计算所有文本内容中的字符数每个字符 = 0.25 token（每个 token 大约 4
        #  个字符）
        #
        total_chars = 0
        for msg in messages:
            for content in msg.content:
                if hasattr(content, "text"):
                    total_chars += len(content.text)
        return total_chars // 4

    mock_llm.get_token_count.side_effect = mock_token_count

    return mock_llm


class TestGetTotalTokenCount:
    """测试 get_total_token_count 功能。"""

    def test_empty_events(self, mock_llm: LLM):
        """使用空事件列表进行测试。"""
        events = []
        token_count = get_total_token_count(events, mock_llm)
        assert token_count == 0

    def test_single_event(self, mock_llm: LLM):
        """使用单个事件进行测试。"""
        events = [message_event("Hello world")]  # 11 个字符 -> 2 token
        token_count = get_total_token_count(events, mock_llm)
        assert token_count == 2

    def test_multiple_events(self, mock_llm: LLM):
        """使用多个事件进行测试。"""
        events = [
            message_event("Hello"),  # 5 个字符 -> 1 token
            message_event("World"),  # 5 个字符 -> 1 token
            message_event("Test message"),  # 12 个字符 -> 3 token
        ]
        token_count = get_total_token_count(events, mock_llm)
        assert token_count == 5  # (5 + 5 + 12) // 4 = 5

    def test_events_converted_to_messages(self, mock_llm: LLM):
        """测试事件是否正确转换为消息。"""
        events = [message_event("Test")]
        get_total_token_count(events, mock_llm)

        # 验证 get_token_count 被调用
        assert mock_llm.get_token_count.called  # type: ignore
        # 验证它是通过消息列表调用的
        call_args = mock_llm.get_token_count.call_args[0][0]  # type: ignore
        assert isinstance(call_args, list)
        assert all(isinstance(msg, Message) for msg in call_args)

    def test_system_prompt_tools_are_counted(self, mock_llm: LLM):
        """测试智能体工具模式是否包含在 token 计数中。"""
        tools = cast(list[ToolDefinition], list(FinishTool.create()))
        events = [
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="system"),
                tools=tools,
            ),
            message_event("Test"),
        ]

        mock_llm.get_token_count.side_effect = None  # type: ignore
        mock_llm.get_token_count.return_value = 7  # type: ignore

        assert get_total_token_count(events, mock_llm) == 7

        kwargs = mock_llm.get_token_count.call_args.kwargs  # type: ignore
        assert kwargs["tools"] == tools
        assert kwargs["add_security_risk_prediction"] is True

    def test_system_prompt_empty_tools_are_not_counted(self, mock_llm: LLM):
        """测试空工具列表不添加工具模式 token。"""
        events = [
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="system"),
                tools=[],
            ),
            message_event("Test"),
        ]

        mock_llm.get_token_count.side_effect = None  # type: ignore
        mock_llm.get_token_count.return_value = 3  # type: ignore

        assert get_total_token_count(events, mock_llm) == 3

        kwargs = mock_llm.get_token_count.call_args.kwargs  # type: ignore
        assert kwargs["tools"] is None
        assert kwargs["add_security_risk_prediction"] is False


class TestGetShortestPrefixAboveTokenCount:
    """测试 get_shortest_prefix_above_token_count 功能。"""

    def test_empty_events(self, mock_llm: LLM):
        """使用空事件列表进行测试。"""
        events = []
        prefix_length = get_shortest_prefix_above_token_count(events, mock_llm, 10)
        assert prefix_length == 0

    def test_no_prefix_exceeds_token_count(self, mock_llm: LLM):
        """当总计 token 不超过目标时进行测试。"""
        events = [
            message_event("Hi"),  # 2 个字符 -> 0 token
            message_event("Bye"),  # 3 个字符 -> 0 token
        ]
        prefix_length = get_shortest_prefix_above_token_count(events, mock_llm, 100)
        assert prefix_length == len(events)

    def test_single_event_exceeds(self, mock_llm: LLM):
        """测试当第一个事件单独超过词元数量时。"""
        events = [
            message_event("A" * 100),  # 100 个字符 -> 25 token
            message_event("B" * 100),  # 100 个字符 -> 25 token
        ]
        prefix_length = get_shortest_prefix_above_token_count(events, mock_llm, 20)
        assert prefix_length == 1

    def test_multiple_events_needed(self, mock_llm: LLM):
        """测试何时需要多个事件超过词元数量。"""
        events = [
            message_event("A" * 20),  # 20 个字符 -> 5 token
            message_event("B" * 20),  # 20 个字符 -> 5 token
            message_event("C" * 20),  # 20 个字符 -> 5 token
            message_event("D" * 20),  # 20 个字符 -> 5 token
        ]
        # 需要 3 个事件的前缀才能超过 10 token (15 > 10)
        prefix_length = get_shortest_prefix_above_token_count(events, mock_llm, 10)
        assert prefix_length == 3

    def test_exact_boundary(self, mock_llm: LLM):
        """在精确的词元数量边界测试行为。"""
        events = [
            message_event("A" * 40),  # 40 个字符 -> 10 token
            message_event("B" * 40),  # 40 个字符 -> 10 token
        ]
        # 10 token 不 > 10，20 token 需要 2 个事件
        prefix_length = get_shortest_prefix_above_token_count(events, mock_llm, 10)
        assert prefix_length == 2

    def test_all_events_needed(self, mock_llm: LLM):
        """当所有事件加起来刚好超过词元数量时进行测试。"""
        events = [
            message_event("A" * 16),  # 16 个字符 -> 4 token
            message_event("B" * 16),  # 16 个字符 -> 4 token
            message_event("C" * 16),  # 16 个字符 -> 4 token
        ]
        # 总共 12 个 token，需要全部 3 个才能超过 10
        prefix_length = get_shortest_prefix_above_token_count(events, mock_llm, 10)
        assert prefix_length == 3


class TestGetSuffixLengthForTokenReduction:
    """测试 get_suffix_length_for_token_reduction 功能。"""

    def test_empty_events(self, mock_llm: LLM):
        """使用空事件列表进行测试。"""
        events = []
        suffix_length = get_suffix_length_for_token_reduction(events, mock_llm, 10)
        assert suffix_length == 0

    def test_zero_token_reduction(self, mock_llm: LLM):
        """要求减少零 token 进行测试。"""
        events = [
            message_event("Test"),
            message_event("Message"),
        ]
        suffix_length = get_suffix_length_for_token_reduction(events, mock_llm, 0)
        assert suffix_length == len(events)

    def test_negative_token_reduction(self, mock_llm: LLM):
        """使用负 token 减少进行测试（边缘情况）。"""
        events = [
            message_event("Test"),
            message_event("Message"),
        ]
        suffix_length = get_suffix_length_for_token_reduction(events, mock_llm, -10)
        assert suffix_length == len(events)

    def test_small_reduction(self, mock_llm: LLM):
        """使用小的 token 减少进行测试，删除很少的事件。"""
        events = [
            message_event("A" * 40),  # 40 个字符 -> 10 token
            message_event("B" * 40),  # 40 个字符 -> 10 token
            message_event("C" * 40),  # 40 个字符 -> 10 token
            message_event("D" * 40),  # 40 个字符 -> 10 token
        ]
        # 总计 40 token，减少 15 表示删除 1 个事件（10 token）后保留后缀。 实际上需要删
        # 除 2 个事件（20 token）才能超过 15 token 减少
        #
        suffix_length = get_suffix_length_for_token_reduction(events, mock_llm, 15)
        assert suffix_length == 2  # 保留最后 2 个事件

    def test_large_reduction(self, mock_llm: LLM):
        """使用大的 token 减少进行测试，以删除大多数事件。"""
        events = [
            message_event("A" * 20),  # 20 个字符 -> 5 token
            message_event("B" * 20),  # 20 个字符 -> 5 token
            message_event("C" * 20),  # 20 个字符 -> 5 token
            message_event("D" * 20),  # 20 个字符 -> 5 token
        ]
        # 总共 20 token，减少 18 token 意味着删除 4 个事件 (20 token)
        suffix_length = get_suffix_length_for_token_reduction(events, mock_llm, 18)
        assert suffix_length == 0  # 什么都不保留

    def test_exact_reduction(self, mock_llm: LLM):
        """使用与某些事件匹配的精确 token 减少进行测试。"""
        events = [
            message_event("A" * 40),  # 40 个字符 -> 10 token
            message_event("B" * 40),  # 40 个字符 -> 10 token
            message_event("C" * 40),  # 40 个字符 -> 10 token
        ]
        # 总计 30 token，减少正好 10 token 需要删除 2 个事件 (20 token) 才能超过 10
        # token 减少
        #
        suffix_length = get_suffix_length_for_token_reduction(events, mock_llm, 10)
        assert suffix_length == 1  # 保留最后 1 个事件

    def test_impossible_reduction(self, mock_llm: LLM):
        """当请求的减少量超过总数 token 时进行测试。"""
        events = [
            message_event("Hi"),  # 2 个字符 -> 0 token
            message_event("Bye"),  # 3 个字符 -> 0 token
        ]
        # 总计 ~0 token，但要求减少 100
        suffix_length = get_suffix_length_for_token_reduction(events, mock_llm, 100)
        assert suffix_length == 0  # 无法保留任何东西

    def test_consistency_with_prefix_function(self, mock_llm: LLM):
        """测试后缀计算与前缀计算是否一致。"""
        events = [
            message_event("A" * 40),  # 40 个字符 -> 10 token
            message_event("B" * 40),  # 40 个字符 -> 10 token
            message_event("C" * 40),  # 40 个字符 -> 10 token
            message_event("D" * 40),  # 40 个字符 -> 10 token
        ]
        token_reduction = 25

        suffix_length = get_suffix_length_for_token_reduction(
            events, mock_llm, token_reduction
        )
        prefix_length = get_shortest_prefix_above_token_count(
            events, mock_llm, token_reduction
        )

        # 后缀+前缀总长度应相等
        assert suffix_length + prefix_length == len(events)

    def test_base_events_are_included_for_prefix_token_counting(self, mock_llm: LLM):
        """token 减少应计算保留事件的上下文中的后缀。"""
        base_events = [
            message_event("system-like prefix"),
            message_event("kept user request"),
        ]
        events = [
            message_event("A" * 40),  # 40 个字符 -> 10 token
            message_event("B" * 40),  # 40 个字符 -> 10 token
            message_event("C" * 40),  # 40 个字符 -> 10 token
        ]

        suffix_length = get_suffix_length_for_token_reduction(
            events,
            mock_llm,
            token_reduction=10,
            base_events=base_events,
        )

        assert suffix_length == 1
        first_counted_messages = mock_llm.get_token_count.call_args_list[0].args[0]  # type: ignore
        counted_text = "\n".join(
            content.text
            for message in first_counted_messages
            for content in message.content
        )
        assert "system-like prefix" in counted_text
        assert "kept user request" in counted_text
