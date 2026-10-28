from collections.abc import Sequence

from openhands.sdk.event.base import LLMConvertibleEvent
from openhands.sdk.event.llm_convertible.system import SystemPromptEvent
from openhands.sdk.llm import LLM


def get_total_token_count(
    events: Sequence[LLMConvertibleEvent],
    llm: LLM,
) -> int:
    """计算 LLM 个可转换事件列表的总数词元数量。

    此函数将事件转换为 LLM 消息，并使用提供的 LLM 来计算 token 的总数。 这对于了解事
    件序列将在上下文窗口中消耗多少 token 很有用。 一个视图预计
    有一个系统提示词事件； 如果存在多个，则仅包括第一个系统提示词的工具。

    Args:
        events: 要计数 token 的 LLM 个可转换事件列表
        llm: 用于 token 计数的 LLM 实例（使用 LiteLLM 的 token
            计算公用事业）

    Returns:
        转换为消息的所有事件总计词元数量

    Example:
        >>> from openhands.sdk.llm import LLM
        >>> from openhands.sdk.event.llm_convertible import MessageEvent
        >>>
        >>> llm = LLM(model="gpt-4")
        >>> events = [
        ...     MessageEvent.from_text("Hello, how are you?", source="user"),
        ...     MessageEvent.from_text("I'm doing great!", source="agent"),
        ... ]
        >>> token_count = get_total_token_count(events, llm)
        >>> print(f"Total tokens: {token_count}")
    """
    messages = LLMConvertibleEvent.events_to_messages(list(events))
    tools = next(
        (event.tools for event in events if isinstance(event, SystemPromptEvent)),
        None,
    )
    return llm.get_token_count(
        messages,
        tools=tools or None,
        # 安全风险 token 始终包含在实际工具请求中。
        add_security_risk_prediction=bool(tools),
    )


def get_shortest_prefix_above_token_count(
    events: Sequence[LLMConvertibleEvent],
    llm: LLM,
    token_count: int,
    base_events: Sequence[LLMConvertibleEvent] | None = None,
) -> int:
    """求词元数量超过目标的最短前缀的长度。

    该函数使用二分查找算法高效地查找事件的最短前缀，该前缀在转换为消息后，总长度词元
    数量大于指定的目标词元数量。

    Args:
        events: 要搜索的 LLM 个可转换事件列表
        llm: 用于 token 计数的 LLM 实例（使用模型的分词器）
        token_count: 目标词元数量阈值

    Returns:
        超过词元数量的最短前缀的长度。 如果未提供事件，则返回 0。 如果所有事件组合不
        超过词元数量，则返回 len(events)。

    Example:
        >>> from openhands.sdk.llm import LLM
        >>> from openhands.sdk.event.llm_convertible import MessageEvent
        >>>
        >>> llm = LLM(model="gpt-4")
        >>> events = [
        ...     MessageEvent.from_text("Hi", source="user"),
        ...     MessageEvent.from_text("Hello", source="agent"),
        ...     MessageEvent.from_text("How are you?", source="user"),
        ...     MessageEvent.from_text("Great!", source="agent"),
        ... ]
        >>> prefix_len = get_shortest_prefix_above_token_count(events, llm, 20)
        >>> # prefix_len 可能是 2，如果前两件事情超过 20 token
    """
    if not events:
        return 0

    base_events = base_events or []
    base_tokens = get_total_token_count(base_events, llm) if base_events else 0

    # 检查所有事件的总和是否不超过词元数量
    total_tokens = get_total_token_count([*base_events, *events], llm) - base_tokens
    if total_tokens <= token_count:
        return len(events)

    # 二分查找最短前缀
    left, right = 1, len(events)

    while left < right:
        mid = (left + right) // 2
        prefix_tokens = (
            get_total_token_count([*base_events, *events[:mid]], llm) - base_tokens
        )

        if prefix_tokens > token_count:
            # 这个前缀超出了计数，尝试找一个更短的
            right = mid
        else:
            # 这个前缀不超过，我们需要一个更长的
            left = mid + 1

    return left


def get_suffix_length_for_token_reduction(
    events: Sequence[LLMConvertibleEvent],
    llm: LLM,
    token_reduction: int,
    base_events: Sequence[LLMConvertibleEvent] | None = None,
) -> int:
    """找出在将 token 减少目标数量的同时可以保留多少个后缀事件。

    该函数确定从列表末尾可以保留的最大事件数量，同时确保总词元数量减少至少指定的金额
    。 它使用
    get_shortest_prefix_above_token_count 函数来查找必须删除的前缀。

    Args:
        events: LLM 可转换事件列表
        llm: 用于 token 计数的 LLM 实例（使用模型的分词器）
        token_reduction: 减少的最小token个数

    Returns:
        从末尾开始可以保留的事件数（后缀长度）。

    Example:
        >>> from openhands.sdk.llm import LLM
        >>> from openhands.sdk.event.llm_convertible import MessageEvent
        >>>
        >>> llm = LLM(model="gpt-4")
        >>> events = [
        ...     MessageEvent.from_text("Event 1", source="user"),
        ...     MessageEvent.from_text("Event 2", source="agent"),
        ...     MessageEvent.from_text("Event 3", source="user"),
        ...     MessageEvent.from_text("Event 4", source="agent"),
        ... ]
        >>> # 假设总和为100 token，我们希望减少40 token
        >>> suffix_len = get_suffix_length_for_token_reduction(events, llm, 40)
        >>> # suffix_len告诉我们我们可以保留多少事件
        >>> # 如果前两个事件为45 token，suffix_len = 2（保留最后两个事件）
    """
    if not events:
        return 0

    if token_reduction <= 0:
        return len(events)

    # 找到超过token缩减目标的最短前缀
    prefix_length = get_shortest_prefix_above_token_count(
        events,
        llm,
        token_reduction,
        base_events=base_events,
    )

    # 后缀长度是去掉前缀后剩下的长度
    suffix_length = len(events) - prefix_length

    return suffix_length
