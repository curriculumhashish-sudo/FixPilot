from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeGuard

from litellm import ChatCompletionToolParam, Message as LiteLLMMessage
from litellm.types.utils import Choices, ModelResponse, StreamingChoices

from openhands.sdk.llm._message_normalization import NonNativeMessageMetadata
from openhands.sdk.llm.exceptions import LLMNoResponseError
from openhands.sdk.llm.mixins.fn_call_converter import (
    STOP_WORDS,
    convert_fncall_messages_to_non_fncall_messages,
    convert_non_fncall_messages_to_fncall_messages,
)
from openhands.sdk.llm.utils.model_features import ModelFeatures


class _HostSupports(Protocol):
    model: str
    disable_stop_word: bool | None
    native_tool_calling: bool

    def _model_features(self) -> ModelFeatures: ...


class NonNativeToolCallingMixin:
    """当本机 FC 关闭时，Mixin 提供提示词-模拟的工具调用支持。

    Host requirements:
    - self.model: 字符串
    - self.disable_stop_word: bool | None
    - self.native_tool_calling -> 布尔值
    """

    def should_mock_tool_calls(
        self: _HostSupports, tools: list[ChatCompletionToolParam] | None
    ) -> bool:
        return bool(tools) and not self.native_tool_calling

    def pre_request_prompt_mock(
        self: _HostSupports,
        messages: list[dict],
        tools: list[ChatCompletionToolParam],
        kwargs: dict,
        include_security_params: bool = False,
    ) -> tuple[list[dict], dict]:
        """当本机工具调用关闭时，转换为非 fncall 提示。"""
        # 对于理解格式或具有有限上下文窗口的模型，跳过上下文学习示例
        #
        add_iclex = not any(
            s in self.model for s in ("openhands-lm", "devstral", "nemotron")
        )
        messages = convert_fncall_messages_to_non_fncall_messages(
            messages,
            tools,
            add_in_context_learning_example=add_iclex,
            include_security_params=include_security_params,
        )
        if self._model_features().supports_stop_words and not self.disable_stop_word:
            kwargs = dict(kwargs)
            kwargs["stop"] = STOP_WORDS

        # 确保我们在模拟时不会发送 tool_choice
        kwargs.pop("tool_choice", None)
        return messages, kwargs

    def post_response_prompt_mock(
        self: _HostSupports,
        resp: ModelResponse,
        nonfncall_msgs: list[dict],
        tools: list[ChatCompletionToolParam],
        include_security_params: bool = False,
    ) -> ModelResponse:
        if len(resp.choices) < 1:
            raise LLMNoResponseError(
                "Response choices is less than 1 (seen in some providers). Resp: "
                + str(resp)
            )

        def _all_choices(
            items: Sequence[Choices | StreamingChoices],
        ) -> TypeGuard[list[Choices]]:
            return all(isinstance(c, Choices) for c in items)

        if not _all_choices(resp.choices):
            raise AssertionError(
                "Expected non-streaming Choices when post-processing mocked tools"
            )

        # 转换前保留提供者特定的推理字段
        orig_msg = resp.choices[0].message
        non_fn_message: dict = orig_msg.model_dump()
        fn_msgs: list[dict] = convert_non_fncall_messages_to_fncall_messages(
            nonfncall_msgs + [non_fn_message],
            tools,
            include_security_params=include_security_params,
        )
        last: dict = fn_msgs[-1]

        metadata = NonNativeMessageMetadata.model_validate(orig_msg)
        if metadata.reasoning_content:
            last["reasoning_content"] = metadata.reasoning_content
        if metadata.provider_specific_fields:
            last["provider_specific_fields"] = metadata.provider_specific_fields

        resp.choices[0].message = LiteLLMMessage.model_validate(last)
        return resp
