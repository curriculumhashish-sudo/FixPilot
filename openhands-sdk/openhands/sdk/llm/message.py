import json
from abc import abstractmethod
from collections.abc import Iterable, Sequence
from typing import Annotated, Any, ClassVar, Literal

from litellm import ChatCompletionMessageToolCall, ResponseFunctionToolCall
from litellm.types.responses.main import OutputFunctionToolCall
from litellm.types.utils import Message as LiteLLMMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhands.sdk.llm._message_normalization import (
    ChatMessageMetadata,
    FunctionOutput,
    MessageOutput,
    ReasoningOutput,
    normalize_response_output,
    normalize_text_part,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.utils import DEFAULT_TEXT_CONTENT_LIMIT, maybe_truncate
from openhands.sdk.utils.deprecation import handle_deprecated_model_fields
from openhands.sdk.utils.masking import PreserveDataUrls


logger = get_logger(__name__)


class MessageToolCall(BaseModel):
    """传输层-不可知的工具调用表示。

    一个规范 ID 用于跨操作/观察和响应 function_call_output call_id 进行链接。
    """

    id: str = Field(..., description="Canonical tool call id")
    responses_item_id: str | None = Field(
        default=None,
        description="Original Responses function_call.id, echoed verbatim on replay",
    )
    name: str = Field(..., description="Tool/function name")
    arguments: str = Field(..., description="JSON string of arguments")
    origin: Literal["completion", "responses"] = Field(
        ..., description="Originating API family"
    )

    @classmethod
    def from_chat_tool_call(
        cls, tool_call: ChatCompletionMessageToolCall
    ) -> "MessageToolCall":
        """从聊天完成工具调用创建 MessageToolCall。"""
        if not tool_call.type == "function":
            raise ValueError(
                f"Unsupported tool call type for {tool_call=}, expected 'function' "
                f"not {tool_call.type}'"
            )
        if tool_call.function is None:
            raise ValueError(f"tool_call.function is None for {tool_call=}")
        if tool_call.function.name is None:
            raise ValueError(f"tool_call.function.name is None for {tool_call=}")

        return cls(
            id=tool_call.id,
            name=tool_call.function.name,
            arguments=tool_call.function.arguments,
            origin="completion",
        )

    @classmethod
    def from_responses_function_call(
        cls, item: ResponseFunctionToolCall | OutputFunctionToolCall
    ) -> "MessageToolCall":
        """从键入的 OpenAI 响应 function_call 项目创建 MessageToolCall。

        Note: OpenAI 响应 function_call.arguments 已经是 JSON 字符串。
        """
        call_id = item.call_id or item.id or ""
        name = item.name or ""
        arguments_str = item.arguments or ""

        if not call_id:
            raise ValueError(f"Responses function_call missing call_id/id: {item!r}")
        if not name:
            raise ValueError(f"Responses function_call missing name: {item!r}")

        return cls(
            id=str(call_id),
            responses_item_id=str(item.id) if item.id else None,
            name=str(name),
            arguments=arguments_str,
            origin="responses",
        )

    def to_chat_dict(self) -> dict[str, Any]:
        """序列化到 OpenAI 聊天完成 tool_calls 格式。"""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }

    def to_responses_dict(self) -> dict[str, Any]:
        """序列化至 OpenAI 响应“function_call”输入项格式。"""
        # 当我们拥有原始的 function_call.id 时，逐字回显它，因此重播保持字节相同，并且
        # OpenAI 的前缀缓存保持匹配。
        #
        item_id = self.responses_item_id or (
            self.id if str(self.id).startswith("fc") else f"fc_{self.id}"
        )
        # 响应要求参数为 JSON 字符串
        args_str = (
            self.arguments
            if isinstance(self.arguments, str)
            else json.dumps(self.arguments)
        )
        return {
            "type": "function_call",
            "id": item_id,
            "call_id": self.id,
            "name": self.name,
            "arguments": args_str,
        }


class ThinkingBlock(BaseModel):
    """Anthropic 思维块用于扩展思维功能。

    这表示启用扩展思维时 Anthropic 模型返回的原始思维块。 这些块必须保留并传回API以供
    工具使用场景使用。
    """

    type: Literal["thinking"] = "thinking"
    thinking: str = Field(..., description="The thinking content")
    signature: str | None = Field(
        default=None, description="Cryptographic signature for the thinking block"
    )


class RedactedThinkingBlock(BaseModel):
    """已脱敏先前回复的思维障碍，没有扩展思考。

    它用作在启用扩展思维之前生成的辅助消息的占位符。
    """

    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str = Field(..., description="The redacted thinking content")


class ReasoningItemModel(BaseModel):
    """OpenAI 响应推理项（非流，我们使用的子集）。

    不记录或渲染 encrypted_content。
    """

    id: str | None = Field(default=None)
    summary: list[str] = Field(default_factory=list)
    content: list[str] | None = Field(default=None)
    encrypted_content: str | None = Field(default=None)
    status: str | None = Field(default=None)


class BaseContent(BaseModel):
    cache_prompt: bool = False

    @abstractmethod
    def to_llm_dict(self) -> list[dict[str, str | dict[str, str]]]:
        """转换为LLMAPI格式。 始终返回字典列表。

        子类应该实现此方法以返回字典列表，即使它们只有一个项目。
        """


class TextContent(BaseContent):
    type: Literal["text"] = "text"
    text: str
    # 我们使用 populate_by_name 因为 mcp.types.TextContent 别名元 -> _meta，但是 .
    # model_dumps() 将输出“meta”
    #
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", populate_by_name=True
    )

    # 加载旧事件时，向后兼容性的已弃用字段将被静默删除。 这些将被永久保留，以确保旧的对
    # 话始终可以加载。
    #
    _DEPRECATED_FIELDS: ClassVar[tuple[str, ...]] = ("enable_truncation",)

    @model_validator(mode="before")
    @classmethod
    def _handle_deprecated_fields(cls, data: Any) -> Any:
        """删除包含旧事件的向后兼容性的已弃用字段。"""
        return handle_deprecated_model_fields(data, cls._DEPRECATED_FIELDS)

    def to_llm_dict(self) -> list[dict[str, str | dict[str, str]]]:
        """转换为LLMAPI格式。"""
        data: dict[str, str | dict[str, str]] = {
            "type": self.type,
            "text": self.text,
        }
        if self.cache_prompt:
            data["cache_control"] = {"type": "ephemeral"}
        return [data]


class ImageContent(BaseContent):
    type: Literal["image"] = "image"
    image_urls: Annotated[list[str], PreserveDataUrls()]

    def to_llm_dict(self) -> list[dict[str, str | dict[str, str]]]:
        """转换为LLMAPI格式。"""
        images: list[dict[str, str | dict[str, str]]] = []
        for url in self.image_urls:
            images.append({"type": "image_url", "image_url": {"url": url}})
        if self.cache_prompt and images:
            images[-1]["cache_control"] = {"type": "ephemeral"}
        return images


class Message(BaseModel):
    # 注意：这与EventSource不同
    # 这些是 LLM 的 APIs 中的角色
    role: Literal["user", "system", "assistant", "tool"]
    content: Sequence[TextContent | ImageContent] = Field(default_factory=list)
    # - 工具调用（来自LLM）
    tool_calls: list[MessageToolCall] | None = None
    # - 工具执行结果（至LLM）
    tool_call_id: str | None = None
    name: str | None = None  # 工具名称
    # 推理内容（来自o1、克劳德思维、DeepSeek R1等推理模型）
    reasoning_content: str | None = Field(
        default=None,
        description="Intermediate reasoning/thinking content from reasoning models",
    )
    # Anthropic特定思维块（未通过LiteLLM标准化）
    thinking_blocks: Sequence[ThinkingBlock | RedactedThinkingBlock] = Field(
        default_factory=list,
        description="Raw Anthropic thinking blocks for extended thinking feature",
    )
    # OpenAI 响应推理项（通过响应 API 输出提供时）
    responses_reasoning_item: ReasoningItemModel | None = Field(
        default=None,
        description="OpenAI Responses reasoning item from model output",
    )

    # 已弃用字段已移至 to_chat_dict() 参数。 当加载旧事件时，这些会被默默地删除向后兼容
    # 性。 永久保留以确保旧对话始终可以加载。
    #
    _DEPRECATED_FIELDS: ClassVar[tuple[str, ...]] = (
        "cache_enabled",
        "vision_enabled",
        "function_calling_enabled",
        "force_string_serializer",
        "send_reasoning_content",
    )

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _handle_deprecated_fields(cls, data: Any) -> Any:
        """删除包含旧事件的向后兼容性的已弃用字段。"""
        return handle_deprecated_model_fields(data, cls._DEPRECATED_FIELDS)

    @property
    def contains_image(self) -> bool:
        return any(isinstance(content, ImageContent) for content in self.content)

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_content(cls, v: Any) -> Sequence[TextContent | ImageContent] | Any:
        # 接受 None → []
        if v is None:
            return []
        # 接受单个字符串 → [TextContent(...)]
        if isinstance(v, str):
            return [TextContent(text=v)]
        return v

    def to_chat_dict(
        self,
        *,
        cache_enabled: bool,
        vision_enabled: bool,
        function_calling_enabled: bool,
        force_string_serializer: bool,
        send_reasoning_content: bool,
    ) -> dict[str, Any]:
        """序列化用于 OpenAI 会话完成的消息。

        Args:
            cache_enabled: 提示词缓存是否处于活动状态。
            vision_enabled: 是否启用视觉/图像处理。
            function_calling_enabled: 是否启用本机函数调用。
            force_string_serializer: 强制使用字符串序列化器而不是列表格式。
            send_reasoning_content: 输出中是否包含 reasoning_content。

        选择适当的内容序列化器，然后注入线程键：
        - 助理工具调用转：角色==“助理”和self.tool_calls
        - 工具结果转：角色==“工具”和self.tool_call_id（带名称）
        """
        # 字符串序列化器仅发出文本，因此它会默默地丢弃图像。 当模型可以接受它们时，即使
        # 强制使用字符串序列化，也保留携带图像内容的消息的列表格式。
        #
        preserve_images = vision_enabled and self.contains_image

        if not force_string_serializer and (
            cache_enabled or vision_enabled or function_calling_enabled
        ):
            message_dict = self._list_serializer(vision_enabled=vision_enabled)
        elif preserve_images:
            message_dict = self._list_serializer(vision_enabled=vision_enabled)
        else:
            # 一些提供商，例如 HF 和 Groq/llama，不支持此处的列表，但支持单个字符串
            #
            message_dict = self._string_serializer()

        # 助理 function_call(s)
        if self.role == "assistant" and self.tool_calls:
            message_dict["tool_calls"] = [tc.to_chat_dict() for tc in self.tool_calls]
            self._remove_content_if_empty(message_dict)
        else:
            self._normalize_empty_assistant_content(message_dict)

        # 工具结果 (观测结果) 螺纹加工
        if self.role == "tool" and self.tool_call_id is not None:
            assert self.name is not None, (
                "name is required when tool_call_id is not None"
            )
            message_dict["tool_call_id"] = self.tool_call_id
            message_dict["name"] = self.name

        # 对于 kimi-k2-thinking 等模型是必需的
        if send_reasoning_content and self.reasoning_content:
            message_dict["reasoning_content"] = self.reasoning_content

        return message_dict

    def _string_serializer(self) -> dict[str, Any]:
        # 将内容转换为单个字符串
        content = "\n".join(
            item.text for item in self.content if isinstance(item, TextContent)
        )
        if self.role == "tool":
            content = self._maybe_truncate_tool_text(content)
        message_dict: dict[str, Any] = {"content": content, "role": self.role}

        # to_chat_dict 中添加了工具调用个键以集中行为
        return message_dict

    def _list_serializer(self, *, vision_enabled: bool) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        role_tool_with_prompt_caching = False

        # 先添加思维块（用于Anthropic扩展思维） 只为辅助消息添加思维块
        #
        thinking_blocks_dicts = []
        if self.role == "assistant":
            thinking_blocks = list(self.thinking_blocks)  # 复制以避免修改原始内容
            for thinking_block in thinking_blocks:
                thinking_dict = thinking_block.model_dump()
                thinking_blocks_dicts.append(thinking_dict)

        for item in self.content:
            # 所有内容类型现在都返回 list[dict[str、Any]]
            item_dicts = item.to_llm_dict()

            if self.role == "tool" and item_dicts:
                for d in item_dicts:
                    text_val = d.get("text")
                    if d.get("type") == "text" and isinstance(text_val, str):
                        d["text"] = self._maybe_truncate_tool_text(text_val)

            # 我们必须删除工具内容的 cache_prompt 并将其移至消息级别，有关详细信息，请参
            # 阅此处的讨论：
            # https://github.com/BerriAI/litellm/issues/6422#issuecomment-2438765472
            #
            if self.role == "tool" and item.cache_prompt:
                role_tool_with_prompt_caching = True
                for d in item_dicts:
                    d.pop("cache_control", None)

            # 处理 ImageContent 的视觉过滤
            if isinstance(item, ImageContent) and vision_enabled:
                content.extend(item_dicts)
            elif not isinstance(item, ImageContent):
                # 添加非图像内容（TextContent等）
                content.extend(item_dicts)

        message_dict: dict[str, Any] = {"content": content, "role": self.role}
        if role_tool_with_prompt_caching:
            message_dict["cache_control"] = {"type": "ephemeral"}

        if thinking_blocks_dicts:
            message_dict["thinking_blocks"] = thinking_blocks_dicts

        # to_chat_dict 中添加了工具调用个键以集中行为
        return message_dict

    def _remove_content_if_empty(self, message_dict: dict[str, Any]) -> None:
        """从辅助工具调用消息中删除空文本内容条目。

        就地改变提供的 message_dict：
        - 如果内容是仅包含空格的字符串，则删除“内容”键
        - 如果内容是列表，则删除任何带有空文本的文本项； 如果列表变空，则删除“内容”键
        """
        if "content" not in message_dict:
            return

        content = message_dict["content"]

        if isinstance(content, str):
            if content.strip() == "":
                message_dict.pop("content", None)
            return

        if isinstance(content, list):
            normalized: list[Any] = []
            for item in content:
                if not isinstance(item, dict):
                    normalized.append(item)
                    continue

                if item.get("type") == "text":
                    text_value = item.get("text", "")
                    if isinstance(text_value, str):
                        if text_value.strip() == "":
                            continue
                    else:
                        raise ValueError(
                            f"Text content item has non-string text value: "
                            f"{text_value!r}"
                        )

                normalized.append(item)

            if normalized:
                message_dict["content"] = normalized
            else:
                message_dict.pop("content", None)
            return

        # 任何其他内容形状均保持原样

    def _normalize_empty_assistant_content(self, message_dict: dict[str, Any]) -> None:
        """标准化聊天完成的空普通助理内容。"""
        if self.role != "assistant":
            return

        if message_dict.get("content") == []:
            message_dict["content"] = ""

    def to_responses_value(self, *, vision_enabled: bool) -> str | list[dict[str, Any]]:
        """返回已序列化表格。

        指令字符串（对于系统）或输入项（对于其他角色）。"""
        if self.role == "system":
            parts: list[str] = []
            for c in self.content:
                if isinstance(c, TextContent) and c.text:
                    parts.append(c.text)
            return "\n".join(parts)
        return self.to_responses_dict(vision_enabled=vision_enabled)

    def to_responses_dict(self, *, vision_enabled: bool) -> list[dict[str, Any]]:
        """序列化 OpenAI 响应消息（输入参数）。

        Delegates to ``llm.utils.responses_serialization``; 请参阅该模块以了解每个角
        色的映射。
        """
        # 延迟导入以打破对 message.py 的循环依赖。
        from openhands.sdk.llm.utils.responses_serialization import (
            message_to_responses_dict,
        )

        return message_to_responses_dict(self, vision_enabled=vision_enabled)

    def _maybe_truncate_tool_text(self, text: str) -> str:
        if not text or len(text) <= DEFAULT_TEXT_CONTENT_LIMIT:
            return text
        logger.warning(
            "Tool TextContent text length (%s) exceeds limit (%s), truncating",
            len(text),
            DEFAULT_TEXT_CONTENT_LIMIT,
        )
        return maybe_truncate(text, DEFAULT_TEXT_CONTENT_LIMIT)

    @classmethod
    def from_llm_chat_message(cls, message: LiteLLMMessage) -> "Message":
        """将 LiteLLMMessage（聊天完成）转换为我们的 Message 类。

        用于推理的与提供者无关的映射：
        - 首选 `message.reasoning_content`（如果存在）（LiteLLM 标准化字段）
        - 从内容数组中提取 `thinking_blocks`（特定于 Anthropic）
        """
        assert message.role != "function", "Function role is not supported"

        metadata = ChatMessageMetadata.model_validate(message)
        thinking_blocks = [
            ThinkingBlock.model_validate(block)
            if block.get("type") == "thinking"
            else RedactedThinkingBlock.model_validate(block)
            for block in metadata.thinking_blocks or []
        ]

        tool_calls = None

        if message.tool_calls:
            # Validate 工具调用 - 过滤掉非函数类型
            if any(tc.type != "function" for tc in message.tool_calls):
                logger.warning(
                    "LLM returned tool calls but some are not of type 'function' - "
                    "ignoring those"
                )

            function_tool_calls = [
                tc for tc in message.tool_calls if tc.type == "function"
            ]

            if len(function_tool_calls) > 0:
                tool_calls = [
                    MessageToolCall.from_chat_tool_call(tc)
                    for tc in function_tool_calls
                ]
            else:
                # 如果过滤后没有留下任何函数工具调用，则引发错误
                raise ValueError(
                    "LLM returned tool calls but none are of type 'function'"
                )

        return Message(
            role=message.role,
            content=[TextContent(text=message.content)]
            if isinstance(message.content, str)
            else [],
            tool_calls=tool_calls,
            reasoning_content=metadata.reasoning_content,
            thinking_blocks=thinking_blocks,
        )

    @classmethod
    def from_llm_responses_output(
        cls,
        output: Iterable[object] | None,
    ) -> "Message":
        """将 OpenAI 响应 API 输出项转换为单个辅助消息。

        政策（非流）：
        - 通过连接消息项目中的 output_text 个部分来收集助理文本
        - 将 function_call 项标准化为 MessageToolCall 列表
        """
        assistant_text_parts: list[str] = []
        tool_calls: list[MessageToolCall] = []
        responses_reasoning_item: ReasoningItemModel | None = None

        for raw_item in output or []:
            item = normalize_response_output(raw_item)
            if isinstance(item, MessageOutput):
                for raw_part in item.content or []:
                    part = normalize_text_part(raw_part)
                    if part is not None and part.text:
                        assistant_text_parts.append(part.text)
            elif isinstance(item, (OutputFunctionToolCall, ResponseFunctionToolCall)):
                tc = MessageToolCall.from_responses_function_call(item)
                tool_calls.append(tc)
            elif isinstance(item, FunctionOutput):
                tc = MessageToolCall.model_validate(
                    {
                        "id": item.call_id or item.id or "",
                        "responses_item_id": str(item.id) if item.id else None,
                        "name": item.name,
                        "arguments": item.arguments,
                        "origin": "responses",
                    }
                )
                tool_calls.append(tc)
            elif isinstance(item, ReasoningOutput):
                responses_reasoning_item = ReasoningItemModel(
                    id=item.id,
                    summary=[part.text for part in item.summary or []],
                    content=[part.text for part in item.content or []] or None,
                    encrypted_content=item.encrypted_content,
                    status=item.status,
                )

        assistant_text = "\n".join(assistant_text_parts).strip()
        return Message(
            role="assistant",
            content=[TextContent(text=assistant_text)] if assistant_text else [],
            tool_calls=tool_calls or None,
            responses_reasoning_item=responses_reasoning_item,
        )


def content_to_str(contents: Sequence[TextContent | ImageContent]) -> list[str]:
    """将 TextContent 和 ImageContent 列表转换为字符串列表。

    这主要用于显示目的。
    """
    text_parts = []
    for content_item in contents:
        if isinstance(content_item, TextContent):
            text_parts.append(content_item.text)
        elif isinstance(content_item, ImageContent):
            text_parts.append(f"[Image: {len(content_item.image_urls)} URLs]")
    return text_parts
