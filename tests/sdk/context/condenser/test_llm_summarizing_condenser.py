from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.types.utils import (
    Choices,
    Message as LiteLLMMessage,
    ModelResponse,
    Usage,
)
from pydantic import SecretStr, ValidationError

from openhands.sdk.context.condenser.base import (
    CondensationRequirement,
    NoCondensationAvailableException,
)
from openhands.sdk.context.condenser.llm_summarizing_condenser import (
    LLMSummarizingCondenser,
    Reason,
)
from openhands.sdk.context.view import View
from openhands.sdk.event.base import Event, LLMConvertibleEvent
from openhands.sdk.event.condenser import Condensation, CondensationRequest
from openhands.sdk.event.llm_convertible import MessageEvent, SystemPromptEvent
from openhands.sdk.llm import (
    LLM,
    LLMResponse,
    Message,
    MetricsSnapshot,
    TextContent,
)


def message_event(content: str) -> MessageEvent:
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


@pytest.fixture
def mock_llm() -> LLM:
    """创建模拟对象 LLM 进行测试。"""
    mock_llm = MagicMock(spec=LLM)

    # 模拟对象完成响应现在返回 LLMResponse
    def create_completion_result(content: str) -> LLMResponse:
        message = Message(role="assistant", content=[TextContent(text=content)])
        metrics = MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=None,
        )
        # 创建模拟对象 ModelResponse
        raw_response = MagicMock(spec=ModelResponse)
        raw_response.id = "mock-llm-response-id"
        return LLMResponse(message=message, metrics=metrics, raw_response=raw_response)

    mock_llm.generate.return_value = create_completion_result(
        "Summary of forgotten events"
    )
    mock_llm.agenerate = AsyncMock(return_value=mock_llm.generate.return_value)
    mock_llm.uses_responses_api = lambda: False
    mock_llm.requires_streaming = False
    mock_llm.format_messages_for_llm = lambda messages: messages

    # 模拟对象 LLM 验证器读取的必需属性
    mock_llm.openrouter_site_url = "https://docs.all-hands.dev/"
    mock_llm.openrouter_app_name = "OpenHands"
    mock_llm.aws_access_key_id = None
    mock_llm.aws_secret_access_key = None
    mock_llm.aws_session_token = None
    mock_llm.aws_region_name = None
    mock_llm.aws_profile_name = None
    mock_llm.aws_role_name = None
    mock_llm.aws_session_name = None
    mock_llm.aws_bedrock_runtime_endpoint = None
    mock_llm.metrics = None
    mock_llm.model = "test-model"
    mock_llm.log_completions = False
    mock_llm.log_completions_folder = None
    mock_llm.custom_tokenizer = None
    mock_llm.base_url = None
    mock_llm.reasoning_effort = None
    mock_llm.litellm_extra_body = {}
    mock_llm.temperature = 0.0
    # 流式传输默认是关闭的（与LLM.stream的默认匹配），所以上下文压缩器直接使用这个LLM而
    # 不复制它。
    #
    mock_llm.stream = False

    # 显式设置 LLM -> 遥测接线所需的定价属性
    mock_llm.input_cost_per_token = None
    mock_llm.output_cost_per_token = None

    mock_llm._metrics = None
    mock_llm._telemetry = None

    # 设置模拟对象响应内容的辅助方法
    def set_mock_response_content(content: str):
        result = create_completion_result(content)
        mock_llm.generate.return_value = result
        mock_llm.agenerate = AsyncMock(return_value=result)

    mock_llm.set_mock_response_content = set_mock_response_content

    return mock_llm


def test_default_values(mock_llm: LLM) -> None:
    """测试 LLMSummarizingCondenser 是否具有正确的默认值。

    这些默认值经过调整以确保上下文压缩的操作索引可行。 请参阅
    https://github.com/OpenHands/software-agent-sdk/issues/1518  中的上下文。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm)

    # 默认 max_size 应为 240（从 120 提高到为工具循环留出更多空间）
    assert condenser.max_size == 240

    # 默认 keep_first 应为 2（从 4 减少，为上下文压缩留出更多空间）
    #
    assert condenser.keep_first == 2


def test_should_condense(mock_llm: LLM) -> None:
    """测试 LLMSummarizingCondenser 是否正确判断何时进行合并。"""
    max_size = 100
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=max_size)

    # 创建低于阈值的事件
    small_events = [message_event(f"Event {i}") for i in range(max_size)]
    small_view = View.from_events(small_events)

    assert condenser.condensation_requirement(small_view) is None

    # 创建高于阈值的事件（触发 EVENTS 原因 -> SOFT 要求）
    large_events = [message_event(f"Event {i}") for i in range(max_size + 1)]
    large_view = View.from_events(large_events)

    assert (
        condenser.condensation_requirement(large_view) == CondensationRequirement.SOFT
    )


def test_condense_returns_view_when_no_condensation_needed(mock_llm: LLM) -> None:
    """测试当不需要上下文压缩时上下文压缩器是否返回原始视图。"""  # noqa: E501
    max_size = 100
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=max_size)

    events: list[Event] = [message_event(f"Event {i}") for i in range(max_size)]
    view = View.from_events(events)

    result = condenser.condense(view)

    assert isinstance(result, View)
    assert result == view
    # LLM 不应被调用
    cast(MagicMock, mock_llm.generate).assert_not_called()


def test_condense_returns_condensation_when_needed(mock_llm: LLM) -> None:
    """测试当需要上下文压缩时，上下文压缩器是否返回上下文压缩。"""
    max_size = 10
    keep_first = 3
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=max_size, keep_first=keep_first
    )

    # 设置模拟对象响应
    cast(Any, mock_llm).set_mock_response_content("Summary of forgotten events")

    events: list[Event] = [message_event(f"Event {i}") for i in range(max_size + 1)]
    view = View.from_events(events)

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    assert result.summary == "Summary of forgotten events"
    # summary_offset 应该是 >= keep_first 的最小操作索引。由于所有事件都是 MessageEvents
    # ，操作索引是 [0,1,2,3,4,...]。最小索引 >= keep_first (3) 是 3，这意味着我们保留事
    # 件 [0:3] = 操作索引 0,1,2 = 3 个事件
    #
    assert result.summary_offset == keep_first
    assert len(result.forgotten_event_ids) > 0

    # LLM 应该被调用一次
    cast(MagicMock, mock_llm.generate).assert_called_once()


def test_get_condensation_with_previous_summary(mock_llm: LLM) -> None:
    """测试上下文压缩器是否正确处理先前的摘要内容。"""
    max_size = 10
    keep_first = 3
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=max_size, keep_first=keep_first
    )

    # 设置模拟对象响应
    cast(Any, mock_llm).set_mock_response_content("Updated summary")

    # 在历史中有一个上下文压缩。需要创建足够多的事件，使得在上下文压缩之后，视图仍然超过
    # max_size 上下文压缩将删除2个事件（事件[3]和事件[4]）加上自身。因此，我们需要至少
    # max_size + 1 + 3 = 14个事件才能超过max_size在上下文压缩之后
    #
    events = [message_event(f"Event {i}") for i in range(14)]

    # 添加上下文压缩来模拟之前的摘要由于 summary_offset，摘要将插入到 keep_first 处
    #
    condensation = Condensation(
        forgotten_event_ids={events[3].id, events[4].id},
        summary="Previous summary content",
        summary_offset=keep_first,
        llm_response_id="condensation_response_1",
    )
    events_with_condensation = (
        events[:keep_first] + [condensation] + events[keep_first:]
    )

    view = View.from_events(events_with_condensation)

    result = condenser.get_condensation(view)

    assert isinstance(result, Condensation)
    assert result.summary == "Updated summary"

    # 验证是否使用之前的摘要调用了 LLM
    completion_mock = cast(MagicMock, mock_llm.generate)
    completion_mock.assert_called_once()
    call_args = completion_mock.call_args
    messages = call_args[1]["messages"]  # 获取关键字参数

    # 汇总指令作为系统消息发送，而要汇总的事件（包括任何先前的汇总）作为用户消息发送。
    #
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    events_text = messages[1].content[0].text

    # 提示词应包含之前的摘要（在 <PREVIOUS SUMMARY> 秒前）。摘要现在是从视图中获取的，应
    # 该在摘要事件中包含它
    #
    assert (
        "Previous summary content" in events_text or "<PREVIOUS SUMMARY>" in events_text
    )


def test_invalid_config(mock_llm: LLM) -> None:
    """测试 LLMSummarizingCondenser 验证配置参数。"""
    # 测试 max_size 必须为阳性
    with pytest.raises(ValueError):
        LLMSummarizingCondenser(llm=mock_llm, max_size=0)

    # 测试 keep_first 必须为非负数
    with pytest.raises(ValueError):
        LLMSummarizingCondenser(llm=mock_llm, keep_first=-1)

    # 测试 keep_first 必须小于 max_size // 2 以便为上下文压缩留出空间
    with pytest.raises(ValueError):
        LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=8)


def test_get_condensation_does_not_pass_extra_body(mock_llm: LLM) -> None:
    """上下文压缩器不应将 extra_body 传递到 llm.generate。

    这可以防止像 1p Anthropic 这样的提供者拒绝带有“extra_body：不允许额外输入”的请求
    。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=2)

    # 准备一个触发上下文压缩 (len > max_size) 的视图
    events: list[Event] = [message_event(f"Event {i}") for i in range(12)]
    view = View.from_events(events)

    result = condenser.condense(view)
    assert isinstance(result, Condensation)

    # 确保在没有显式 extra_body kwarg 的情况下调用完成
    completion_mock = cast(MagicMock, mock_llm.generate)
    assert completion_mock.call_count == 1


def test_condense_with_agent_llm(mock_llm: LLM) -> None:
    """测试上下文压缩器接受并使用可选的智能体 llm 参数。"""
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=2)

    # 为智能体的 LLM 创建单独的模拟对象
    agent_llm = MagicMock(spec=LLM)
    agent_llm.model = "gpt-4"
    agent_llm.effective_max_input_tokens = None

    # 准备一个触发上下文压缩的视图
    events: list[Event] = [message_event(f"Event {i}") for i in range(12)]
    view = View.from_events(events)

    # 使用智能体的 LLM 调用压缩
    result = condenser.condense(view, agent_llm=agent_llm)
    assert isinstance(result, Condensation)

    # 验证上下文压缩器仍然使用自己的 LLM 进行汇总
    completion_mock = cast(MagicMock, mock_llm.generate)
    assert completion_mock.call_count == 1

    # 智能体 LLM 不应被调用来完成（上下文压缩器使用其自己的 LLM）
    assert not agent_llm.generate.called
    _, kwargs = completion_mock.call_args
    assert "extra_body" not in kwargs


def test_condense_with_token_limit_exceeded(mock_llm: LLM) -> None:
    """测试当超出 token 限制时，上下文压缩器是否因 TOKENS 原因触发。"""
    max_tokens = 100
    keep_first = 2
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=1000, max_tokens=max_tokens, keep_first=keep_first
    )

    # 为智能体的 LLM 创建一个单独的模拟对象，并使用 token 计数
    agent_llm = MagicMock(spec=LLM)
    agent_llm.model = "gpt-4"
    agent_llm.effective_max_input_tokens = None

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

    cast(MagicMock, agent_llm.get_token_count).side_effect = mock_token_count

    # 创建超过 token 限制的事件每个事件有 40 个字符 = 10 token 15 个事件 = 150 token（超
    # 过 100 个 max_tokens）
    #
    events: list[Event] = [message_event("A" * 40) for i in range(15)]
    view = View.from_events(events)

    # 验证 TOKENS 是上下文压缩原因
    reasons = condenser.get_condensation_reasons(view, agent_llm=agent_llm)
    assert Reason.TOKENS in reasons
    assert Reason.EVENTS not in reasons  # 不应在事件计数时触发
    assert Reason.REQUEST not in reasons

    # 凝练视图
    result = condenser.condense(view, agent_llm=agent_llm)
    assert isinstance(result, Condensation)

    # 验证上下文压缩器使用自己的 LLM 进行摘要
    completion_mock = cast(MagicMock, mock_llm.generate)
    assert completion_mock.call_count == 1

    # 验证遗忘事件是根据 token 减少计算的
    assert len(result.forgotten_event_ids) > 0


@pytest.mark.parametrize(
    ("configured_limit", "agent_limit", "token_count", "expected_trigger"),
    [(500, 100, 200, True), (100, 500, 200, True), (100, 500, 50, False)],
)
def test_token_limit_uses_stricter_configured_or_agent_limit(
    mock_llm: LLM,
    configured_limit: int,
    agent_limit: int,
    token_count: int,
    expected_trigger: bool,
) -> None:
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=1000, max_tokens=configured_limit, keep_first=2
    )
    agent_llm = MagicMock(spec=LLM)
    agent_llm.effective_max_input_tokens = agent_limit
    agent_llm.get_token_count.return_value = token_count

    view = View.from_events([message_event("event") for _ in range(10)])

    reasons = condenser.get_condensation_reasons(view, agent_llm=agent_llm)

    assert (Reason.TOKENS in reasons) is expected_trigger


def test_token_limit_inherits_agent_effective_input_limit(
    mock_llm: LLM,
) -> None:
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=1000, keep_first=2)
    agent_llm = MagicMock(spec=LLM)
    agent_llm.effective_max_input_tokens = 100
    agent_llm.get_token_count.return_value = 200

    view = View.from_events([message_event("event") for _ in range(10)])

    reasons = condenser.get_condensation_reasons(view, agent_llm=agent_llm)

    assert Reason.TOKENS in reasons


def test_token_reduction_uses_agent_effective_input_limit(mock_llm: LLM) -> None:
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=1000, max_tokens=500, keep_first=2
    )
    agent_llm = MagicMock(spec=LLM)
    agent_llm.effective_max_input_tokens = 100
    agent_llm.get_token_count.return_value = 200

    view = View.from_events([message_event("event") for _ in range(10)])

    forgotten_events, _ = condenser._get_forgotten_events(view, agent_llm=agent_llm)

    assert forgotten_events


def test_condense_with_request_and_events_reasons(mock_llm: LLM) -> None:
    """当 REQUEST 和 EVENTS 原因同时为 True 时，测试上下文压缩。

    验证是否选择了最具攻击性的上下文压缩（最小后缀）。
    """
    max_size = 20
    keep_first = 2
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=max_size, keep_first=keep_first
    )

    # 创建超过 max_size AND 的事件，包括上下文压缩请求 25 个事件 > max_size，共 20 个（
    # 触发器 EVENTS） 加上 CondensationRequest（触发器 REQUEST）
    #
    events: list[Event] = [message_event(f"Event {i}") for i in range(25)]
    events.append(CondensationRequest())
    view = View.from_events(events)

    # 验证两个原因都存在
    reasons = condenser.get_condensation_reasons(view, agent_llm=None)
    assert Reason.REQUEST in reasons
    assert Reason.EVENTS in reasons
    assert Reason.TOKENS not in reasons

    # 获取上下文压缩
    result = condenser.condense(view)
    assert isinstance(result, Condensation)

    # 计算预期行为：
    # REQUEST: target_size = len(view) // 2 = 25 // 2 = 12
    #          suffix_to_keep = 12 - keep_first - 1 = 12 - 2 - 1 = 9
    # EVENTS:  target_size = max_size // 2 = 20 // 2 = 10
    #          suffix_to_keep = 10 - keep_first - 1 = 10 - 2 - 1 = 7
    # 最激进：min(9, 7) = 7

    # 操纵指数为 MessageEvents：
    # naive_start = keep_first = 2
    # naive_end = 25 - 7 = 18
    # manipulation_indices = [0, 1, 2, 3, ..., 25]
    # forgetting_start = smallest index >= keep_first = 2
    # forgetting_end = smallest index >= naive_end = 18
    # 被遗忘：事件[2:18] = 16 个事件
    expected_forgotten_count = 16
    assert len(result.forgotten_event_ids) == expected_forgotten_count


def test_condense_with_request_and_tokens_reasons(mock_llm: LLM) -> None:
    """当 REQUEST 和 TOKENS 原因同时为 True 时，测试上下文压缩。

    验证是否选择了最具攻击性的上下文压缩（最小后缀）。
    """
    max_tokens = 100
    keep_first = 2
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=1000, max_tokens=max_tokens, keep_first=keep_first
    )

    # 为智能体的 LLM 创建一个单独的模拟对象，并使用 token 计数
    agent_llm = MagicMock(spec=LLM)
    agent_llm.model = "gpt-4"
    agent_llm.effective_max_input_tokens = None

    # 模拟对象 get_token_count 返回可预测的值
    def mock_token_count(messages, **_kwargs):
        total_chars = 0
        for msg in messages:
            for content in msg.content:
                if hasattr(content, "text"):
                    total_chars += len(content.text)
        return total_chars // 4

    cast(MagicMock, agent_llm.get_token_count).side_effect = mock_token_count

    # 创建 20 个事件，每个事件 40 个字符 = 10 token 每个 = 200 总计 token 这超过了 100
    # 中的 max_tokens（触发 TOKENS）
    #
    events: list[Event] = [message_event("A" * 40) for i in range(20)]
    # 添加 CondensationRequest（触发 REQUEST）
    events.append(CondensationRequest())
    view = View.from_events(events)

    # 验证两个原因都存在
    reasons = condenser.get_condensation_reasons(view, agent_llm=agent_llm)
    assert Reason.REQUEST in reasons
    assert Reason.TOKENS in reasons
    assert Reason.EVENTS not in reasons

    # 获取上下文压缩
    result = condenser.condense(view, agent_llm=agent_llm)
    assert isinstance(result, Condensation)

    # 应选择最具攻击性的上下文压缩（最小后缀）
    assert len(result.forgotten_event_ids) > 0


def test_condense_with_events_and_tokens_reasons(mock_llm: LLM) -> None:
    """当 EVENTS 和 TOKENS 原因同时为 True 时，测试上下文压缩。

    验证是否选择了最具攻击性的上下文压缩（最小后缀）。
    """
    max_size = 15
    max_tokens = 100
    keep_first = 2
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=max_size, max_tokens=max_tokens, keep_first=keep_first
    )

    # 为智能体的 LLM 创建一个单独的模拟对象，并使用 token 计数
    agent_llm = MagicMock(spec=LLM)
    agent_llm.model = "gpt-4"
    agent_llm.effective_max_input_tokens = None

    def mock_token_count(messages, **_kwargs):
        total_chars = 0
        for msg in messages:
            for content in msg.content:
                if hasattr(content, "text"):
                    total_chars += len(content.text)
        return total_chars // 4

    cast(MagicMock, agent_llm.get_token_count).side_effect = mock_token_count

    # 创建 20 个事件（超过 15 个中的 max_size），每个事件 40 个字符 20 个事件 * 10 token
    #  = 200 token（超过 100 个中的 max_tokens）
    #
    events: list[Event] = [message_event("A" * 40) for i in range(20)]
    view = View.from_events(events)

    # 验证两个原因都存在
    reasons = condenser.get_condensation_reasons(view, agent_llm=agent_llm)
    assert Reason.EVENTS in reasons
    assert Reason.TOKENS in reasons
    assert Reason.REQUEST not in reasons

    # 获取上下文压缩
    result = condenser.condense(view, agent_llm=agent_llm)
    assert isinstance(result, Condensation)

    # 应选择最具攻击性的上下文压缩（最小后缀）
    assert len(result.forgotten_event_ids) > 0


def test_condense_with_all_three_reasons(mock_llm: LLM) -> None:
    """当所有三个原因同时为 True 时，测试上下文压缩。

    验证当 REQUEST、EVENTS 和 TOKENS 全部同时触发时，是否选择了最具攻击性的上下文压缩
    （最小后缀）。
    """
    max_size = 15
    max_tokens = 100
    keep_first = 2
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=max_size, max_tokens=max_tokens, keep_first=keep_first
    )

    # 为智能体的 LLM 创建一个单独的模拟对象，并使用 token 计数
    agent_llm = MagicMock(spec=LLM)
    agent_llm.model = "gpt-4"
    agent_llm.effective_max_input_tokens = None

    def mock_token_count(messages, **_kwargs):
        total_chars = 0
        for msg in messages:
            for content in msg.content:
                if hasattr(content, "text"):
                    total_chars += len(content.text)
        return total_chars // 4

    cast(MagicMock, agent_llm.get_token_count).side_effect = mock_token_count

    # 创建 20 个事件（超过 15 个中的 max_size），每个事件 40 个字符 20 个事件 * 10 token
    #  = 200 token（超过 100 个中的 max_tokens）
    #
    events: list[Event] = [message_event("A" * 40) for i in range(20)]
    # 添加 CondensationRequest（触发 REQUEST）
    events.append(CondensationRequest())
    view = View.from_events(events)

    # 验证所有三个原因都存在
    reasons = condenser.get_condensation_reasons(view, agent_llm=agent_llm)
    assert Reason.REQUEST in reasons
    assert Reason.EVENTS in reasons
    assert Reason.TOKENS in reasons

    # 获取上下文压缩
    result = condenser.condense(view, agent_llm=agent_llm)
    assert isinstance(result, Condensation)

    # 应选择最具攻击性的上下文压缩（最小后缀）这意味着应该忘记最多的事件
    #
    assert len(result.forgotten_event_ids) > 0

    # 验证上下文压缩器使用自己的 LLM 进行摘要
    completion_mock = cast(MagicMock, mock_llm.generate)
    assert completion_mock.call_count == 1


def test_most_aggressive_condensation_chosen(mock_llm: LLM) -> None:
    """测试当多个原因提供不同的结果时，是否选择最小后缀
    目标。

    此测试显式验证上下文压缩器第 200 行的 min() 逻辑。
    """
    max_size = 30  # 设置高，以便 EVENTS 触发特定目标
    keep_first = 2
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=max_size, keep_first=keep_first
    )

    # 创建一个场景，其中 REQUEST 和 EVENTS 给出不同的后缀大小总共 40 个事件
    #
    events: list[Event] = [message_event(f"Event {i}") for i in range(40)]
    events.append(CondensationRequest())
    view = View.from_events(events)

    # 计算预期后缀长度：
    # REQUEST: target_size = len(view) // 2 = 40 // 2 = 20
    #          suffix_to_keep = 20 - keep_first - 1 = 20 - 2 - 1 = 17
    # EVENTS:  target_size = max_size // 2 = 30 // 2 = 15
    #          suffix_to_keep = 15 - keep_first - 1 = 15 - 2 - 1 = 12
    # 最激进：min(17, 12) = 12

    result = condenser.condense(view)
    assert isinstance(result, Condensation)

    # 操纵指数为 MessageEvents：
    # naive_start = keep_first = 2
    # naive_end = 40 - 12 = 28
    # manipulation_indices = [0, 1, 2, 3, ..., 40]
    # forgetting_start = smallest index >= keep_first = 2
    # forgetting_end = smallest index >= naive_end = 28
    # 被遗忘的事件： events[2:28] = 26 个事件
    expected_forgotten_count = 26
    assert len(result.forgotten_event_ids) == expected_forgotten_count


def test_generate_condensation_raises_on_zero_events(mock_llm: LLM) -> None:
    """测试当给定 0 个事件时 _generate_condensation 是否引发 AssertionError。

    这防止了 LLM 被空事件列表调用，这会产生一个令人困惑的总结，如“我未提供任何事件来
    总结”。请参阅
    https://github.com/OpenHands/software-agent-sdk/issues/1518  以了解上下文。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=100, keep_first=2)

    with pytest.raises(AssertionError, match="No events to condense"):
        condenser._generate_condensation(
            forgotten_events=[],
            summary_offset=0,
        )

    # 验证 LLM 从未被调用过
    cast(MagicMock, mock_llm.generate).assert_not_called()


@pytest.mark.parametrize(
    "reasons",
    [set()],
)
def test_condensation_requirement_returns_none(
    mock_llm: LLM, reasons: set[Reason]
) -> None:
    """测试 condensation_requirement 在适当的时候返回 None。

    模拟对象 get_condensation_reasons 测试不同的原因组合。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=100, keep_first=2)
    events: list[Event] = [message_event(f"Event {i}") for i in range(10)]
    view = View.from_events(events)

    with patch.object(
        LLMSummarizingCondenser, "get_condensation_reasons", return_value=reasons
    ):
        result = condenser.condensation_requirement(view)
        assert result is None


@pytest.mark.parametrize(
    "reasons",
    [
        {Reason.EVENTS},
    ],
)
def test_condensation_requirement_returns_soft(
    mock_llm: LLM, reasons: set[Reason]
) -> None:
    """测试 condensation_requirement 返回 SOFT 以表示资源限制。

    模拟对象 get_condensation_reasons 测试不同的资源原因组合。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=100, keep_first=2)
    events: list[Event] = [message_event(f"Event {i}") for i in range(10)]
    view = View.from_events(events)

    with patch.object(
        LLMSummarizingCondenser, "get_condensation_reasons", return_value=reasons
    ):
        result = condenser.condensation_requirement(view)
        assert result == CondensationRequirement.SOFT


@pytest.mark.parametrize(
    "reasons",
    [
        {Reason.TOKENS},
        {Reason.TOKENS, Reason.EVENTS},
    ],
)
def test_condensation_requirement_returns_hard_for_token_pressure(
    mock_llm: LLM, reasons: set[Reason]
) -> None:
    """token 压力应在下一个 LLM 请求溢出之前触发。"""
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=100, keep_first=2)
    events: list[Event] = [message_event(f"Event {i}") for i in range(10)]
    view = View.from_events(events)

    with patch.object(
        LLMSummarizingCondenser, "get_condensation_reasons", return_value=reasons
    ):
        result = condenser.condensation_requirement(view)
        assert result == CondensationRequirement.HARD


@pytest.mark.parametrize(
    "reasons",
    [
        {Reason.REQUEST},
        {Reason.REQUEST, Reason.TOKENS},
        {Reason.REQUEST, Reason.EVENTS},
        {Reason.REQUEST, Reason.TOKENS, Reason.EVENTS},
    ],
)
def test_condensation_requirement_returns_hard(
    mock_llm: LLM, reasons: set[Reason]
) -> None:
    """测试当 REQUEST 存在时，condensation_requirement 是否返回 HARD。

    模拟对象 get_condensation_reasons 测试与 REQUEST 的不同组合。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=100, keep_first=2)
    events: list[Event] = [message_event(f"Event {i}") for i in range(10)]
    view = View.from_events(events)

    with patch.object(
        LLMSummarizingCondenser, "get_condensation_reasons", return_value=reasons
    ):
        result = condenser.condensation_requirement(view)
        assert result == CondensationRequirement.HARD


def test_condense_with_hard_requirement_and_no_condensation_available(
    mock_llm: LLM,
) -> None:
    """测试压缩会在硬性要求但没有上下文压缩的情况下引发错误。

    当存在硬性要求但没有可用的有效上下文压缩范围（e.g.，整个视图是单个原子单元）时，
    应引发异常。
    """
    from openhands.sdk.context.condenser.base import NoCondensationAvailableException

    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=100, keep_first=2)
    events: list[Event] = [message_event(f"Event {i}") for i in range(10)]
    view = View.from_events(events)

    # 模拟对象返回 HARD 要求，但没有要压缩的事件另外模拟对象 hard_context_reset 返回
    # None，因此重新引发异常
    #
    with (
        patch.object(
            LLMSummarizingCondenser,
            "get_condensation_reasons",
            return_value={Reason.REQUEST},
        ),
        patch.object(condenser, "_get_forgotten_events", return_value=([], 0)),
        patch.object(LLMSummarizingCondenser, "hard_context_reset", return_value=None),
    ):
        with pytest.raises(NoCondensationAvailableException):
            condenser.condense(view)


def test_condense_with_soft_requirement_and_no_condensation_available(
    mock_llm: LLM,
) -> None:
    """测试 condense 返回具有软要求但没有上下文压缩的视图。

    当有软要求但没有有效的上下文压缩范围可用时，应返回原始视图不变。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=100, keep_first=2)
    events: list[Event] = [message_event(f"Event {i}") for i in range(10)]
    view = View.from_events(events)

    # 模拟对象返回 SOFT 要求，但没有要压缩的事件
    with (
        patch.object(
            LLMSummarizingCondenser,
            "get_condensation_reasons",
            return_value={Reason.EVENTS},
        ),
        patch.object(condenser, "_get_forgotten_events", return_value=([], 0)),
    ):
        result = condenser.condense(view)
        assert isinstance(result, View)
        assert result == view
        # LLM 不应被调用
        cast(MagicMock, mock_llm.generate).assert_not_called()


def test_minimum_progress_default_value(mock_llm: LLM) -> None:
    """测试 minimum_progress 是否具有正确的默认值。"""
    condenser = LLMSummarizingCondenser(llm=mock_llm)
    assert condenser.minimum_progress == 0.1


def test_minimum_progress_custom_value(mock_llm: LLM) -> None:
    """测试 minimum_progress 是否接受自定义值。"""
    condenser = LLMSummarizingCondenser(llm=mock_llm, minimum_progress=0.2)
    assert condenser.minimum_progress == 0.2


@pytest.mark.parametrize(
    "invalid_value",
    [
        0.0,  # 必须 > 0.0
        -0.1,  # 必须 > 0.0
        1.0,  # 必须 < 1.0
        1.5,  # 必须 < 1.0
    ],
)
def test_minimum_progress_validation(mock_llm: LLM, invalid_value: float) -> None:
    """测试 minimum_progress 是否验证范围 (0.0 < 值 < 1.0)。"""
    with pytest.raises(ValueError):
        LLMSummarizingCondenser(llm=mock_llm, minimum_progress=invalid_value)


def test_minimum_progress_threshold_not_met(mock_llm: LLM) -> None:
    """测试当被遗忘的事件低于 minimum_progress 时上下文压缩升高。

    当遗忘事件占总事件的比例小于minimum_progress时，应提高
    NoCondensationAvailableException。
    """
    # 创建具有高 minimum_progress 值的上下文压缩器
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=10, keep_first=2, minimum_progress=0.8
    )

    # 创建包含 100 个事件的视图
    events: list[Event] = [message_event(f"Event {i}") for i in range(100)]
    events.append(CondensationRequest())
    view = View.from_events(events)

    # 模拟对象 _get_forgotten_events 返回少量遗忘事件。这允许我们直接测试
    # minimum_progress 阈值检查，而无需处理复杂的边界计算
    #
    small_forgotten = [events[2], events[3]]  # 仅忘记了 2 个事件

    with patch.object(
        condenser, "_get_forgotten_events", return_value=(small_forgotten, 2)
    ):
        # 忘记计数 (2) << minimum_progress (0.8) * len(view) (100) 2 < 80，因此未满足阈
        # 值
        #
        with pytest.raises(NoCondensationAvailableException, match="minimum progress"):
            condenser.get_condensation(view)


def test_minimum_progress_threshold_met(mock_llm: LLM) -> None:
    """当被遗忘的事件满足 minimum_progress 时，测试上下文压缩是否成功。

    当遗忘事件与总事件的比例 >= minimum_progress 时，上下文压缩应该正常进行。
    """
    # 使用较低的 minimum_progress，这样很容易达到阈值
    condenser = LLMSummarizingCondenser(
        llm=mock_llm, max_size=20, keep_first=2, minimum_progress=0.1
    )

    # 设置模拟对象响应
    cast(Any, mock_llm).set_mock_response_content("Summary of forgotten events")

    # 创建足够的事件来触发 EVENTS 个原因（超过 max_size=20） 30 个事件，target_size = 20
    #  // 2 = 10
    #
    # suffix_to_keep = 10 - keep_first - 1 = 10 - 2 - 1 = 7
    # forgotten = 30 - 7 = 23 events
    # 23/30 = 0.77 > 0.1，因此满足minimum_progress
    events: list[Event] = [message_event(f"Event {i}") for i in range(30)]
    view = View.from_events(events)

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    assert result.summary == "Summary of forgotten events"


def test_generate_condensation_wraps_llm_errors(mock_llm: LLM) -> None:
    """LLM _generate_condensation 中的失败引发 NoCondensationAvailableException。"""  # noqa: E501
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=2)

    cast(MagicMock, mock_llm.generate).side_effect = RuntimeError("boom")

    events: list[Event] = [message_event(f"Event {i}") for i in range(12)]
    view = View.from_events(events)

    with pytest.raises(NoCondensationAvailableException, match="boom"):
        condenser.get_condensation(view)


@pytest.mark.asyncio
async def test_agenerate_condensation_wraps_llm_errors(mock_llm: LLM) -> None:
    """异步变体：LLM 故障表面与 NoCondensationAvailableException 相同。"""
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=2)

    cast(MagicMock, mock_llm.agenerate).side_effect = RuntimeError("boom")

    events: list[Event] = [message_event(f"Event {i}") for i in range(12)]
    view = View.from_events(events)

    with pytest.raises(NoCondensationAvailableException, match="boom"):
        await condenser.aget_condensation(view)


def test_llm_error_triggers_hard_context_reset(mock_llm: LLM) -> None:
    """condense() 触发 hard_context_reset 期间摘要器 LLM 失败。"""
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=2)

    # 通过 CondensationRequest 强制 HARD 上下文压缩要求
    events: list[Event] = [message_event(f"Event {i}") for i in range(12)]
    events.append(CondensationRequest())
    view = View.from_events(events)

    # 第一次调用（get_condensation路径）失败； 第二次调用（hard_context_reset路径）成功
    # 。
    #
    success_response = cast(Any, mock_llm).generate.return_value
    cast(MagicMock, mock_llm.generate).side_effect = [
        RuntimeError("context window exceeded"),
        success_response,
    ]

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    assert result.summary == "Summary of forgotten events"
    assert cast(MagicMock, mock_llm.generate).call_count == 2


def _streaming_llm() -> LLM:
    """启用了流式传输的真实 LLM，就像长时间运行的对话一样。"""
    return LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="summarizer-test",
        stream=True,
    )


def _summary_response(content: str = "A summary") -> ModelResponse:
    return ModelResponse(
        id="resp-id",
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(content=content, role="assistant"),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@patch("openhands.sdk.llm.llm.LLM._transport_call", autospec=True)
def test_summarization_disables_streaming_when_llm_streams(mock_transport) -> None:
    """回归测试问题 #3902：``stream=True`` LLM 仍必须总结
    即使上下文压缩器没有通过 ``on_token`` 回调。"""
    mock_transport.return_value = _summary_response("A summary")

    llm = _streaming_llm()
    condenser = LLMSummarizingCondenser(llm=llm, max_size=10, keep_first=3)

    events: list[Event] = [message_event(f"Event {i}") for i in range(11)]
    view = View.from_events(events)

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    assert result.summary == "A summary"
    mock_transport.assert_called_once()
    # 流式传输在副本上被禁用，而不是智能体自己的 LLM （autospec => self 是第一个位置参数
    # ）。
    #
    assert mock_transport.call_args.kwargs["enable_streaming"] is False
    assert mock_transport.call_args.kwargs["on_token"] is None
    summarizing_llm = mock_transport.call_args.args[0]
    assert summarizing_llm is not llm
    assert summarizing_llm.stream is False
    assert llm.stream is True  # 原始未受影响（model_copy 是非变异）
    # 词元用量仍然被计算在内：副本共享原始的指标。
    usage = llm.metrics.accumulated_token_usage
    assert usage is not None
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.LLM._atransport_call", new_callable=AsyncMock)
async def test_async_summarization_disables_streaming_when_llm_streams(
    mock_atransport,
) -> None:
    """异步问题 #3902 的变体回归测试 (aget_condensation)。"""
    mock_atransport.return_value = _summary_response("A summary")

    llm = _streaming_llm()
    condenser = LLMSummarizingCondenser(llm=llm, max_size=10, keep_first=3)

    events: list[Event] = [message_event(f"Event {i}") for i in range(11)]
    view = View.from_events(events)

    result = await condenser.aget_condensation(view)

    assert isinstance(result, Condensation)
    assert result.summary == "A summary"
    mock_atransport.assert_awaited_once()
    assert mock_atransport.call_args.kwargs["enable_streaming"] is False
    assert mock_atransport.call_args.kwargs["on_token"] is None
    assert llm.stream is True


@patch("openhands.sdk.llm.llm.LLM._transport_call", autospec=True)
def test_summarization_uses_llm_as_is_when_not_streaming(mock_transport) -> None:
    """当流式传输关闭时，上下文压缩器进行汇总，LLM 不变。"""
    mock_transport.return_value = _summary_response("A summary")

    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="summarizer-test",
        stream=False,
    )
    condenser = LLMSummarizingCondenser(llm=llm, max_size=10, keep_first=3)

    events: list[Event] = [message_event(f"Event {i}") for i in range(11)]
    view = View.from_events(events)

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    assert result.summary == "A summary"
    # 使用完全相同的 LLM 实例（非流式传输时不复制）。
    assert mock_transport.call_args.args[0] is llm


# --------------------------------------------------------------------------- #
# 回归测试：系统消息必须引导每个压缩请求（#5148/#5149）
# --------------------------------------------------------------------------- #


def _system_prompt_event(
    text: str = "You are a helpful assistant.",
) -> SystemPromptEvent:
    return SystemPromptEvent(system_prompt=TextContent(text=text), tools=[])


def _applied_messages(condensation: Condensation, view: View) -> list[Message]:
    """将上下文压缩应用到视图并将结果投影到 LLM 消息。"""
    applied = condensation.apply(list(view.events))
    return LLMConvertibleEvent.events_to_messages(applied)


def test_hard_context_reset_preserves_leading_system_prompt(mock_llm: LLM) -> None:
    """硬上下文重置必须将 SystemPromptEvent 保持在开头。

    回归对 #5149 的描述：硬复位路径用于在偏移量 0 处总结整个视图（包括系统提示词），
    然后产生一个用户角色摘要作为第一个消息。 现在必须使用保留的系统消息打开它
    。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=2)

    cast(Any, mock_llm).set_mock_response_content("Hard reset summary")

    events: list[Event] = [
        _system_prompt_event("You are a safe assistant."),
        *[message_event(f"Event {i}") for i in range(12)],
    ]
    events.append(CondensationRequest())
    view = View.from_events(events)

    # 强制 get_condensation 路径失败，以便 hard_context_reset 运行。
    success_response = cast(Any, mock_llm).generate.return_value
    cast(MagicMock, mock_llm).generate.side_effect = [
        RuntimeError("context window exceeded"),
        success_response,
    ]

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    assert result.summary_offset == 1  # 摘要放在系统提示词之后
    # 系统提示词被保留，而不是被遗忘。
    assert events[0].id not in result.forgotten_event_ids
    messages = _applied_messages(result, view)
    assert messages[0].role == "system"


@pytest.mark.asyncio
async def test_ahard_context_reset_preserves_leading_system_prompt(
    mock_llm: LLM,
) -> None:
    """异步硬上下文重置也必须首先保留系统提示词。"""
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=2)

    cast(Any, mock_llm).set_mock_response_content("Hard reset summary")

    events: list[Event] = [
        _system_prompt_event(),
        *[message_event(f"Event {i}") for i in range(12)],
    ]
    view = View.from_events(events)

    result = await condenser.ahard_context_reset(view)

    assert isinstance(result, Condensation)
    assert result.summary_offset == 1
    assert events[0].id not in result.forgotten_event_ids
    messages = _applied_messages(result, view)
    assert messages[0].role == "system"


def test_condensation_with_keep_first_zero_keeps_system_first(mock_llm: LLM) -> None:
    """keep_first=0 must not let the SystemPromptEvent be forgotten.

    回归对于 #5148：即使 ``keep_first`` 配置为 0，压缩视图仍必须打开并显示系统消息。
    """
    condenser = LLMSummarizingCondenser(llm=mock_llm, max_size=10, keep_first=0)

    cast(Any, mock_llm).set_mock_response_content("Summary of forgotten events")

    events: list[Event] = [
        _system_prompt_event(),
        *[message_event(f"Event {i}") for i in range(11)],
    ]
    view = View.from_events(events)

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    messages = _applied_messages(result, view)
    assert messages[0].role == "system"
    # 遗忘集不得包括主导系统提示词事件。
    assert events[0].id not in result.forgotten_event_ids


def test_llm_summarizing_condenser_get_llm() -> None:
    """LLMSummarizingCondenser 需要 LLM 并公开 get_llm()。"""
    assert LLMSummarizingCondenser.model_fields["llm"].is_required()

    my_llm = LLM(model="test-condenser-model")
    summarizing = LLMSummarizingCondenser(llm=my_llm)
    assert summarizing.llm is not None
    assert summarizing.llm.model == "test-condenser-model"
    assert summarizing.get_llm() is summarizing.llm

    summarizing.llm = my_llm.model_copy(update={"model": "updated-model"})
    assert summarizing.llm.model == "updated-model"
    updated_llm = summarizing.get_llm()
    assert updated_llm is not None
    assert updated_llm.model == "updated-model"


def test_llm_summarizing_condenser_requires_llm() -> None:
    """LLMSummarizingCondenser 会抛出 ValidationError。"""
    with pytest.raises(ValidationError):
        LLMSummarizingCondenser()  # type: ignore[call-arg]
