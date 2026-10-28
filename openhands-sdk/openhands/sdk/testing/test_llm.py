"""TestLLM - A 模拟对象 LLM 用于测试。

TestLLM 是一个真正的 LLM 子类，它返回脚本化响应，消除了对 @patch 装饰器的需要和对
LiteLLM 内部结构的理解。

Example:
    >>> from openhands.sdk.testing import TestLLM
    >>> from openhands.sdk.llm import Message, TextContent
    >>>
    >>> # 创建一个 TestLLM，并设置脚本响应
    >>> llm = TestLLM.from_messages([
    ...     Message(role="assistant", content=[TextContent(text="Hello!")]),
    ...     Message(role="assistant", content=[TextContent(text="Goodbye!")]),
    ... ])
    >>>
    >>> # 像正常一样使用它 LLM
    >>> user_msg = Message(role="user", content=[TextContent(text="Hi")])
    >>> response = llm.completion([user_msg])
    >>> print(response.message.content[0].text)  # 你好！

    >>> # unittest.mock side_effect 生成的错误
    >>> from openhands.sdk.llm.exceptions import LLMContextWindowExceedError
    >>> llm = TestLLM.from_responses([
    ...     Message(role="assistant", content=[TextContent(text="OK")]),
    ...     LLMContextWindowExceedError(),
    ... ])
    >>> llm.completion([...])  # 返回 "OK"
    >>> llm.completion([...])  # LLMContextWindowExceedError引发了异常
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse
from pydantic import ConfigDict, Field, PrivateAttr

from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.llm_response import LLMResponse
from openhands.sdk.llm.message import Message
from openhands.sdk.llm.streaming import AnyTokenCallbackType, TokenCallbackType
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLMCallContext
    from openhands.sdk.tool.tool import ToolDefinition

from collections import deque


__all__ = ["TestLLM", "TestLLMExhaustedError"]


class TestLLMExhaustedError(Exception):
    """当 TestLLM 没有更多脚本响应时引发。"""

    pass


class TestLLM(LLM):
    """用于返回脚本响应的测试的模拟对象 LLM。

    TestLLM 是一个真正的 LLM 子类，可以在任何接受 LLM 的地方使用：在 Agent(llm=...)、
    fallback_llms、上下文压缩器、路由器等
    中。

    主要特点：
    - 无需修补：只需将 TestLLM 作为 llm= 参数传递
    - 测试以 SDK 类型说话（消息、TextContent、MessageToolCall）
    - 当响应用尽时清除错误
    - 默认情况下的零成本指标
    - 始终使用 completion() 路径（uses_responses_api 返回 False）

    Example:
        >>> from openhands.sdk.testing import TestLLM
        >>> from openhands.sdk.llm import Message, TextContent, MessageToolCall
        >>>
        >>> # 简单的文本回复
        >>> llm = TestLLM.from_messages([
        ...     Message(role="assistant", content=[TextContent(text="Done!")]),
        ... ])
        >>>
        >>> # 工具调用的响应
        >>> llm = TestLLM.from_messages([
        ...     Message(
        ...         role="assistant",
        ...         content=[TextContent(text="")],
        ...         tool_calls=[
        ...             MessageToolCall(
        ...                 id="call_1",
        ...                 name="my_tool",
        ...                 arguments='{"arg": "value"}',
        ...                 origin="completion",
        ...             )
        ...         ],
        ...     ),
        ...     Message(role="assistant", content=[TextContent(text="Done!")]),
        ... ])
    """

    # 阻止 pytest 收集此类作为测试
    __test__ = False

    model: str = Field(default="test-model")
    _scripted_responses: deque[Message | Exception] = PrivateAttr(default_factory=deque)
    _call_count: int = PrivateAttr(default=0)

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="ignore", arbitrary_types_allowed=True
    )

    def __init__(self, **data: Any) -> None:
        # 在调用 super().__init__ 之前提取 scripted_responses
        scripted_responses = data.pop("scripted_responses", [])
        super().__init__(**data)
        self._scripted_responses = deque(list(scripted_responses))
        self._call_count = 0

    @classmethod
    def from_messages(
        cls,
        messages: list[Message | Exception],
        *,
        model: str = "test-model",
        usage_id: str = "test-llm",
        **kwargs: Any,
    ) -> TestLLM:
        """创建一个包含脚本化响应和/或错误的 TestLLM。

        Args:
            messages: 按顺序返回的消息或异常对象的列表。
                每次调用 completion() 或 responses() 都会消耗下一个
                item: 消息对象正常返回，异常对象
                被提升（如 unittest.mock side_effect）。
            model: 模型名称（默认：“测试模型”）
            usage_id: 指标的使用 ID（默认值：“test-llm”）
            **kwargs: 其他 LLM 配置选项

        Returns:
            配置有脚本响应的 TestLLM 实例。

        Example:
            >>> llm = TestLLM.from_messages([
            ...     Message(role="assistant", content=[TextContent(text="First")]),
            ...     LLMContextWindowExceedError("context too long"),
            ... ])
        """
        return cls(
            model=model,
            usage_id=usage_id,
            scripted_responses=messages,
            **kwargs,
        )

    def completion(
        self,
        messages: list[Message],  # noqa: ARG002
        tools: Sequence[ToolDefinition] | None = None,  # noqa: ARG002
        add_security_risk_prediction: bool = False,  # noqa: ARG002
        on_token: TokenCallbackType | None = None,  # noqa: ARG002
        call_context: LLMCallContext | None = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> LLMResponse:
        """返回下一个脚本响应。

        Args:
            messages: 输入消息（被忽略，但 API 兼容性所必需）
            tools: 可用工具（忽略）
            add_security_risk_prediction: 添加安全风险字段（忽略）
            on_token: 流式传输回调 (ignored)
            **kwargs: 附加参数（忽略）

        Returns:
            LLMResponse 包含下一个脚本消息。

        Raises:
            TestLLMExhaustedError: 当没有更多可用的脚本响应时。
            Exception: 放置在响应队列中的任何脚本化异常。
        """
        if not self._scripted_responses:
            raise TestLLMExhaustedError(
                f"TestLLM: no more scripted responses "
                f"(exhausted after {self._call_count} calls)"
            )

        item = self._scripted_responses.popleft()
        self._call_count += 1

        # 引发脚本异常（如 unittest.mock side_effect）
        if isinstance(item, Exception):
            raise item

        message = item

        # 为 raw_response 创建最小 ModelResponse
        raw_response = self._create_model_response(message)

        return LLMResponse(
            message=message,
            metrics=self._zero_metrics(),
            raw_response=raw_response,
        )

    async def acompletion(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        add_security_risk_prediction: bool = False,
        on_token: AnyTokenCallbackType | None = None,  # noqa: ARG002
        call_context: LLMCallContext | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> LLMResponse:
        """异步变体委托给同步：meth:`completion`。

        运行同步调用，以确保事件循环不受阻，尽管底层``deque.popleft()``实际上非常快。

        ``on_token`` 因 API 兼容性而被接受，但未转发，因为：meth:`completion` 会忽略
        它，并且类型联合 (同步 | 异步回调) 不
        可分配给仅同步签名。
        """
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.completion(
                messages=messages,
                tools=tools,
                add_security_risk_prediction=add_security_risk_prediction,
                **kwargs,
            ),
        )

    def responses(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        include: list[str] | None = None,  # noqa: ARG002
        store: bool | None = None,  # noqa: ARG002
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> LLMResponse:
        """返回下一个脚本响应（委托完成）。

        对于 TestLLM，completion() 和 responses() 都从同一脚本响应队列返回。
        """
        return self.completion(
            messages=messages,
            tools=tools,
            add_security_risk_prediction=add_security_risk_prediction,
            on_token=on_token,
            **kwargs,
        )

    def uses_responses_api(self) -> bool:
        """TestLLM 始终使用完成路径。"""
        return False

    def _zero_metrics(self) -> MetricsSnapshot:
        """返回零成本指标快照。"""
        return MetricsSnapshot(
            model_name=self.model,
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=TokenUsage(
                model=self.model,
                prompt_tokens=0,
                completion_tokens=0,
            ),
        )

    def _create_model_response(self, message: Message) -> ModelResponse:
        """从消息创建最小的 ModelResponse。

        这创建了一个有效的 ModelResponse，可以用于 raw_response 在 LLMResponse。
        """
        # 构建 LiteLLM 消息字典
        litellm_message_dict: dict[str, Any] = {
            "role": message.role,
            "content": self._content_to_string(message),
        }

        # 添加 tool_calls（如果存在）
        if message.tool_calls:
            litellm_message_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        litellm_message = LiteLLMMessage(**litellm_message_dict)

        return ModelResponse(
            id=f"test-response-{self._call_count}",
            choices=[Choices(message=litellm_message, index=0, finish_reason="stop")],
            created=0,
            model=self.model,
            object="chat.completion",
        )

    def _content_to_string(self, message: Message) -> str:
        """将消息内容转换为字符串。"""
        from openhands.sdk.llm.message import TextContent

        parts = []
        for item in message.content:
            if isinstance(item, TextContent):
                parts.append(item.text)
        return "\n".join(parts)

    @property
    def remaining_responses(self) -> int:
        """返回剩余脚本响应的数量。"""
        return len(self._scripted_responses)

    @property
    def call_count(self) -> int:
        """返回对此 TestLLM 的调用次数。"""
        return self._call_count
