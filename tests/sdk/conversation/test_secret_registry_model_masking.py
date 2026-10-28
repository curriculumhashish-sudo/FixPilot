"""单元测试对应 SecretRegistry.mask_secrets_in_model（问题 #4677）。"""

import base64
from enum import Enum
from typing import NamedTuple

import mcp.types
from pydantic import BaseModel, SecretStr

from openhands.sdk.conversation.secret_registry import SecretRegistry
from openhands.sdk.llm import ImageContent
from openhands.sdk.mcp import MCPToolObservation


SECRET = "sk-supersecret-value"
MASK = "<secret-hidden>"


class Kind(str, Enum):
    ADD = "add"


class Span(NamedTuple):
    label: str
    line: int


class Inner(BaseModel):
    note: str
    kind: Kind = Kind.ADD


class Outer(BaseModel):
    title: str
    inner: Inner
    items: list[str] = []
    mapping: dict[str, str] = {}
    count: int = 0
    blob: bytes = b""
    opaque: SecretStr | None = None
    tags: set[str] = set()
    span: Span | None = None


def _registry() -> SecretRegistry:
    registry = SecretRegistry()
    registry.update_secrets({"TOKEN": SECRET})
    registry.get_secret_value("TOKEN")  # 解析 -> 跟踪掩码
    return registry


def test_masks_nested_models_lists_and_dict_values():
    model = Outer(
        title=f"title {SECRET}",
        inner=Inner(note=f"note {SECRET}"),
        items=[f"a {SECRET}", "b"],
        mapping={"k": f"v {SECRET}"},
    )

    masked = _registry().mask_secrets_in_model(model)

    assert masked.title == f"title {MASK}"
    assert masked.inner.note == f"note {MASK}"
    assert masked.items == [f"a {MASK}", "b"]
    assert masked.mapping == {"k": f"v {MASK}"}
    assert SECRET not in masked.model_dump_json()


def test_leaves_non_string_values_alone():
    model = Outer(title="clean", inner=Inner(note="clean"), count=7, blob=b"raw")

    masked = _registry().mask_secrets_in_model(model)

    assert masked.count == 7
    assert masked.blob == b"raw"


def test_preserves_str_subclass_enum_members():
    """str 子类枚举必须保留为枚举成员。

    屏蔽它会将其降级为普通的 ``str`` 并破坏该领域的序列化，而且它的词汇表无论如何都无
    法容纳机密。
    """
    model = Outer(title="clean", inner=Inner(note="clean", kind=Kind.ADD))

    masked = _registry().mask_secrets_in_model(model)

    assert masked.inner.kind is Kind.ADD
    assert isinstance(masked.inner.kind, Kind)


def test_secretstr_is_not_walked_as_a_string():
    model = Outer(title="clean", inner=Inner(note="clean"), opaque=SecretStr(SECRET))

    masked = _registry().mask_secrets_in_model(model)

    assert isinstance(masked.opaque, SecretStr)
    assert masked.opaque.get_secret_value() == SECRET


def test_returns_input_unchanged_when_nothing_is_registered():
    model = Outer(title=f"title {SECRET}", inner=Inner(note="clean"))

    masked = SecretRegistry().mask_secrets_in_model(model)

    assert masked.title == f"title {SECRET}"


def test_masks_set_members():
    """``set`` 字段像任何其他容器一样被遍历。"""
    model = Outer(
        title="clean", inner=Inner(note="clean"), tags={f"t {SECRET}", "plain"}
    )

    masked = _registry().mask_secrets_in_model(model)

    assert masked.tags == {f"t {MASK}", "plain"}


def test_preserves_namedtuple_type():
    """NamedTuple 保留其类型，就像枚举保留其成员一样。"""
    model = Outer(title="clean", inner=Inner(note="clean"), span=Span(f"s {SECRET}", 3))

    masked = _registry().mask_secrets_in_model(model)

    assert isinstance(masked.span, Span)
    assert masked.span.label == f"s {MASK}"
    assert masked.span.line == 3


def _base64_payload() -> str:
    return base64.b64encode(b"abc").decode()


def test_preserves_data_image_urls_but_masks_regular_image_urls():
    payload = _base64_payload()
    registry = SecretRegistry()
    registry.update_secrets({"TOKEN": payload})
    registry.get_secret_value("TOKEN")
    content = ImageContent(
        image_urls=[
            f"data:image/png;base64,{payload}",
            f"https://example.com/{payload}.png",
        ]
    )

    masked = registry.mask_secrets_in_model(content)

    assert masked.image_urls == [
        f"data:image/png;base64,{payload}",
        f"https://example.com/{MASK}.png",
    ]


def test_preserves_mcp_image_data_url():
    payload = _base64_payload()
    registry = SecretRegistry()
    registry.update_secrets({"TOKEN": payload})
    registry.get_secret_value("TOKEN")
    result = mcp.types.CallToolResult(
        content=[
            mcp.types.ImageContent(type="image", data=payload, mimeType="image/png")
        ]
    )
    observation = MCPToolObservation.from_call_tool_result("image_tool", result)

    masked = registry.mask_secrets_in_model(observation)

    image_content = masked.content[-1]
    assert isinstance(image_content, ImageContent)
    assert image_content.image_urls == [f"data:image/png;base64,{payload}"]
