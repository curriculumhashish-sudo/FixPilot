from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk.llm import LLM, ImageContent, Message, TextContent


@pytest.mark.parametrize(
    "model",
    [
        # 简单的型号名称
        "claude-sonnet-4-5-20250929",
        "gemini-2.5-flash",
        "gemini-3.1-pro-preview",
        # 带有提供者/代理前缀
        "anthropic/claude-sonnet-4-5-20250929",
        "litellm_proxy/anthropic/claude-sonnet-4-5-20250929",
        "litellm_proxy/gemini-2.5-flash",
        "litellm_proxy/gemini-3.1-pro-preview",
        "kimi-k3",
        "moonshot/kimi-k3",
        "litellm_proxy/moonshot/kimi-k3",
        "openhands/kimi-k3",
    ],
)
def test_vision_is_active_supported_models(model):
    # 使用真正的 LiteLLM 助手（无修补/模拟）。 此测试根据 LiteLLM 的当前知识库验证我们的
    #  vision_is_active 检测（前缀剥离 + model_info 回退方案），无需提供程序调用。
    #
    llm = LLM(model=model, api_key=SecretStr("k"), usage_id="t")
    assert llm.vision_is_active() is True


@patch(
    "openhands.sdk.llm.llm.get_litellm_model_info",
    return_value={"supports_vision": True},
)
@patch(
    "openhands.sdk.llm.utils.model_features.litellm_supports_vision",
    return_value=False,
)
def test_proxy_model_info_can_enable_vision(_mock_sv, _mock_model_info):
    llm = LLM(
        model="litellm_proxy/custom-vision-model",
        api_key=SecretStr("k"),
        usage_id="t",
    )
    assert llm.vision_is_active() is True


def _collect_image_url_parts(chat_message: dict) -> list[dict]:
    content = chat_message.get("content", [])
    return [
        p
        for p in content
        if isinstance(p, dict)
        and p.get("type") == "image_url"
        and isinstance(p.get("image_url"), dict)
        and p["image_url"].get("url")
    ]


def _has_input_image(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("type") != "message":
        return False
    for c in item.get("content", []):
        if isinstance(c, dict) and c.get("type") == "input_image":
            return True
    return False


@pytest.mark.parametrize(
    "model",
    [
        "claude-sonnet-4-5-20250929",
        "gemini-2.5-flash",
        "gemini-3.1-pro-preview",
    ],
)
def test_chat_serializes_images_when_vision_supported(model):
    llm = LLM(model=model, api_key=SecretStr("k"), usage_id="t")
    assert llm.vision_is_active() is True

    msg = Message(
        role="user",
        content=[
            TextContent(text="see image"),
            ImageContent(image_urls=["https://example.com/image.png"]),
        ],
    )
    formatted = llm.format_messages_for_llm([msg])
    assert isinstance(formatted, list) and len(formatted) == 1

    parts = _collect_image_url_parts(formatted[0])
    assert len(parts) >= 1


@patch(
    "openhands.sdk.llm.llm.get_litellm_model_info",
    return_value={"supports_vision": True},
)
@patch(
    "openhands.sdk.llm.utils.model_features.litellm_supports_vision",
    return_value=False,
)
def test_deepseek_v4_vision_payload_keeps_image(_mock_sv, _mock_model_info):
    """具有视觉功能的 DeepSeek v4 模型将其图像部分保留在载荷中。"""
    llm = LLM(
        model="openhands/deepseek-v4.1-flash",
        api_key=SecretStr("k"),
        usage_id="t",
    )
    assert llm.vision_is_active() is True

    msg = Message(
        role="user",
        content=[
            TextContent(text="see image"),
            ImageContent(image_urls=["https://example.com/image.png"]),
        ],
    )
    formatted = llm.format_messages_for_llm([msg])

    assert len(formatted) == 1
    assert len(_collect_image_url_parts(formatted[0])) == 1


@patch(
    "openhands.sdk.llm.llm.get_litellm_model_info",
    return_value={"supports_vision": False},
)
@patch(
    "openhands.sdk.llm.utils.model_features.litellm_supports_vision",
    return_value=False,
)
def test_message_with_image_does_not_enable_vision_for_text_only_model(
    mock_sv, _mock_model_info
):
    # 对于不支持视觉的模型，图像不应该是已序列化。
    llm = LLM(model="text-only-model", api_key=SecretStr("k"), usage_id="t")
    formatted = llm.format_messages_for_llm(
        [
            Message(
                role="user",
                content=[
                    TextContent(text="see image"),
                    ImageContent(image_urls=["https://example.com/image.png"]),
                ],
            )
        ]
    )
    assert isinstance(formatted, list) and len(formatted) == 1
    content = formatted[0]["content"]
    # 由于模型不支持视觉，因此预计不会有 image_url 条目
    assert all(
        not (
            isinstance(part, dict)
            and part.get("type") == "image_url"
            and isinstance(part.get("image_url"), dict)
            and part["image_url"].get("url")
        )
        for part in content
    )


def test_disable_vision_overrides_litellm_detection():
    """测试 disable_vision=True 是否覆盖 LiteLLM 的视觉能力检测。

    这对于像 glm-4.7 这样的模型很重要，其中 LiteLLM 错误地报告了视觉支持，但实际的
    API (OpenRouter) 只接受文本输入。
    """
    # LiteLLM 将通过 OpenRouter 的 glm-4.7 报告为具有视觉能力，但我们明确禁用视觉以防止
    # API 错误
    #
    llm = LLM(
        model="litellm_proxy/openrouter/z-ai/glm-4.7",
        api_key=SecretStr("k"),
        usage_id="t",
        disable_vision=True,
    )

    # 尽管有 LiteLLM 报告支持，但仍应禁用视力
    assert llm.vision_is_active() is False

    # 带有图像的消息不应包含 image_url 部分
    msg = Message(
        role="user",
        content=[
            TextContent(text="see image"),
            ImageContent(image_urls=["https://example.com/image.png"]),
        ],
    )
    formatted = llm.format_messages_for_llm([msg])
    assert isinstance(formatted, list) and len(formatted) == 1

    # 验证格式化消息中没有 image_url 部分
    parts = _collect_image_url_parts(formatted[0])
    assert len(parts) == 0


@patch(
    "openhands.sdk.llm.llm.get_litellm_model_info",
    return_value={"supports_vision": False},
)
@patch(
    "openhands.sdk.llm.utils.model_features.litellm_supports_vision",
    return_value=False,
)
def test_message_with_image_in_responses_does_not_include_input_image(
    mock_sv, _mock_model_info
):
    llm = LLM(model="text-only-model", api_key=SecretStr("k"), usage_id="t")

    instructions, input_items = llm.format_messages_for_responses(
        [
            Message(
                role="user",
                content=[
                    TextContent(text="see image"),
                    ImageContent(image_urls=["https://example.com/image.png"]),
                ],
            )
        ]
    )


@pytest.mark.parametrize(
    "model",
    [
        "claude-sonnet-4-5-20250929",
        "gemini-2.5-flash",
        "gemini-3.1-pro-preview",
    ],
)
def test_responses_serializes_images_when_vision_supported(model):
    llm = LLM(model=model, api_key=SecretStr("k"), usage_id="t")
    assert llm.vision_is_active() is True

    msg = Message(
        role="user",
        content=[
            TextContent(text="see image"),
            ImageContent(image_urls=["https://example.com/image.png"]),
        ],
    )
    instructions, input_items = llm.format_messages_for_responses([msg])
    assert instructions is None or isinstance(instructions, str)

    assert any(_has_input_image(item) for item in input_items)
