import copy
from abc import ABC
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from pydantic import ConfigDict, Field, PrivateAttr, create_model
from rich.text import Text

from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.llm.message import content_to_str
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.models import (
    DiscriminatedUnionMixin,
)
from openhands.sdk.utils.visualize import display_json


if TYPE_CHECKING:
    from typing import Self

logger = get_logger(__name__)

S = TypeVar("S", bound="Schema")


def py_type(spec: dict[str, Any]) -> Any:
    """将 JSON 模式类型映射到 Python 类型。"""
    t = spec.get("type")

    # 将 ["string"、"null"] 等联合类型规范为单个代表类型。 MCP 模式通常以这种方式标记可
    # 选字段； 我们保留非null类型。
    #
    if isinstance(t, (list, tuple, set)):
        types = list(t)
        non_null = [tp for tp in types if tp != "null"]
        if len(non_null) == 1:
            t = non_null[0]
        else:
            return Any
    if t == "array":
        items = spec.get("items", {})
        inner = py_type(items) if isinstance(items, dict) else Any
        return list[inner]  # type: ignore[index]
    if t == "object":
        return dict[str, Any]
    _map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }
    if t in _map:
        return _map[t]
    return Any


def _shallow_expand_circular_ref(ref_def: dict[str, Any]) -> dict[str, Any]:
    """返回一个简单的回退方案以进行循环引用。

    Args:
        ref_def: 引用类型的定义。

    Returns:
        通用对象模式，如果可用，则保留描述。
    """
    result: dict[str, Any] = {"type": "object"}
    if "description" in ref_def:
        result["description"] = ref_def["description"]
    return result


def _process_schema_node(
    node: dict[str, Any] | bool,
    defs: dict[str, Any],
    _visiting: frozenset[str] | None = None,
) -> dict[str, Any]:
    """递归处理模式节点，简化解析$ref。

    此函数解析 JSON 模式 $ref 引用并简化模式结构以与 MCP 工具模式兼容。 它通过跟踪访
    问的引用并在检测到循环时停止递归来处理循环引用。

    Args:
        node: 要处理的模式节点。
        defs: $defs 字典包含参考定义。
        _visiting: 当前正在处理的内部参数跟踪参考
            在当前递归路径中检测循环。

    Returns:
        已解析 $ref 的简化模式字典（循环引用除外）。

    Note:
        当检测到循环引用时，返回一个通用的
        ``{"type": "object"}`` 占位符（如果可用，则保留描述）。 这可以防止无限递归，
        但会丢失有关递归结构的类型信息。 调用者应该意识到，递归
        数据类型（树、链表）将具有简化的模式，可能无法完全代表其结构。

    References:
        https://www.reddit.com/r/mcp/comments/1kjo9gt/toolinputschema_conversion_from_pydanticmodel/
        https://gist.github.com/leandromoreira/3de4819e4e4df9422d87f1d3e7465c16
    """  # noqa: E501
    if _visiting is None:
        _visiting = frozenset()

    # JSON 模式布尔值：`true` 接受任何值，`false` 接受 None。
    if isinstance(node, bool):
        return {} if node else {"not": {}}

    # 处理 $ref 引用
    if "$ref" in node:
        ref_path = node["$ref"]
        if ref_path.startswith("#/$defs/"):
            ref_name = ref_path.split("/")[-1]
            if ref_name in defs:
                # 检查循环引用 - 如果我们已经在当前路径中访问此引用，请不要递归（会导致
                # 无限循环）
                #
                if ref_name in _visiting:
                    logger.debug(
                        "Circular reference detected for '%s', using shallow expansion",
                        ref_name,
                    )
                    # 返回通用对象以防止无限递归
                    return _shallow_expand_circular_ref(defs[ref_name])

                # 将此引用添加到此递归路径的访问集中
                new_visiting = _visiting | {ref_name}
                # 处理引用的定义
                return _process_schema_node(defs[ref_name], defs, new_visiting)

    # 从一个新的模式对象开始
    result: dict[str, Any] = {}

    # 复制基本属性
    if "type" in node:
        result["type"] = node["type"]

    # 句柄 anyOf（通常用于带有 None 的可选字段）
    if "anyOf" in node:
        non_null_types = [
            t
            for t in node["anyOf"]
            if t is True or (isinstance(t, dict) and t.get("type") != "null")
        ]
        if not non_null_types and any(t is False for t in node["anyOf"]):
            # 每个分支拒绝：保留`false`的reject-all含义，而不是默默地将参数扩大为accept-
            # all。
            #
            non_null_types = [False]
        if non_null_types:
            # 处理第一个非null类型
            processed = _process_schema_node(non_null_types[0], defs, _visiting)
            result.update(processed)

    # Handle description
    if "description" in node:
        result["description"] = node["description"]

    # 递归处理对象属性
    if node.get("type") == "object" and "properties" in node:
        result["type"] = "object"
        result["properties"] = {}

        # 处理每个属性
        for prop_name, prop_schema in node["properties"].items():
            result["properties"][prop_name] = _process_schema_node(
                prop_schema, defs, _visiting
            )

        # 添加必填字段（如果存在）
        if "required" in node:
            result["required"] = node["required"]

    # 处理数组
    if node.get("type") == "array" and "items" in node:
        result["type"] = "array"
        result["items"] = _process_schema_node(node["items"], defs, _visiting)

    # 手柄枚举
    if "enum" in node:
        result["enum"] = node["enum"]

    return result


class Schema(DiscriminatedUnionMixin):
    """用于输入操作/输出观测结果的底座模式。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
    mcp_schema_alias_specs: ClassVar[dict[str, dict[str, Any]]] = {}
    mcp_schema_alias_required: ClassVar[set[str]] = set()

    @classmethod
    def _discriminator_field_names(cls) -> set[str]:
        return set(DiscriminatedUnionMixin.model_fields.keys()) | set(
            DiscriminatedUnionMixin.model_computed_fields.keys()
        )

    @classmethod
    def to_mcp_schema(cls) -> dict[str, Any]:
        """转换为与MCP兼容的JSON模式格式。"""
        full_schema = cls.model_json_schema()
        # 这将摆脱模式中的所有“anyOf”，因此它与MCP工具模式完全兼容
        #
        result = _process_schema_node(full_schema, full_schema.get("$defs", {}))

        # 从属性中删除鉴别器字段（不适用于 LLM） 需要排除常规字段和计算字段（如“kind”）
        #
        exclude_fields = cls._discriminator_field_names()
        explicit_mcp_aliases = {
            field_info.alias
            for field_name, field_info in cls.model_fields.items()
            if field_info.alias and field_info.alias != field_name
        }
        for f in exclude_fields:
            if (
                "properties" in result
                and f in result["properties"]
                and f not in explicit_mcp_aliases
            ):
                result["properties"].pop(f)
                # 如果存在，也从必需的中删除
                if "required" in result and f in result["required"]:
                    result["required"].remove(f)

        alias_specs: dict[str, dict[str, Any]] = cls.mcp_schema_alias_specs
        if alias_specs:
            result.setdefault("properties", {})
            for alias, spec in alias_specs.items():
                result["properties"][alias] = _process_schema_node(
                    copy.deepcopy(spec),
                    full_schema.get("$defs", {}),
                )

            alias_required: set[str] = cls.mcp_schema_alias_required
            if alias_required:
                required_fields = result.setdefault("required", [])
                for alias in alias_required:
                    if alias not in required_fields:
                        required_fields.append(alias)

        return result

    @classmethod
    def from_mcp_schema(
        cls: type[S], model_name: str, schema: dict[str, Any]
    ) -> type["S"]:
        """从 MCP/JSON 模式对象创建模式子类。

        对于非必填字段，我们注释为 `T | None`，因此允许显式空值。
        """
        assert isinstance(schema, dict), "Schema must be a dict"
        assert schema.get("type") == "object", "Only object schemas are supported"

        props: dict[str, Any] = schema.get("properties", {}) or {}
        required = set(schema.get("required", []) or [])

        fields: dict[str, tuple] = {}
        discriminator_fields = cls._discriminator_field_names()
        used_field_names = set(props.keys())
        has_aliased_field = False
        alias_specs: dict[str, dict[str, Any]] = {}
        alias_required: set[str] = set()
        for fname, spec in props.items():
            spec = spec if isinstance(spec, dict) else {}
            tp = py_type(spec)

            # 添加描述（如果存在）
            desc: str | None = spec.get("description")
            field_name = fname
            field_alias = None
            if fname in discriminator_fields:
                # MCP 工具参数名称是用户定义的 JSON 对象键。 如果与 OpenHands' 内部鉴别
                # 器 (e.g. “kind”），将外部名称保留为别名，并为 Pydantic 使用安全的内部
                # 字段名称。
                #
                field_alias = fname
                has_aliased_field = True
                alias_specs[fname] = copy.deepcopy(spec)
                if fname in required:
                    alias_required.add(fname)
                field_name = f"mcp_arg_{fname}"
                suffix = 2
                while field_name in used_field_names or field_name in fields:
                    field_name = f"mcp_arg_{fname}_{suffix}"
                    suffix += 1

            # 必需 → 裸类型，省略号哨兵值可选 → 通过 `| None` 设为可为空，默认 None
            #
            if fname in required:
                anno = tp
                default = ...
            else:
                anno = tp | None  # 除了省略之外还允许显式 null
                default = None

            field_kwargs: dict[str, Any] = {}
            if desc:
                field_kwargs["description"] = desc
            if field_alias:
                field_kwargs["alias"] = field_alias

            fields[field_name] = (
                anno,
                Field(default=default, **field_kwargs),
            )

        field_definitions: Any = fields
        if has_aliased_field:
            model = create_model(  # type: ignore[reportCallIssue, return-value]
                model_name,
                __base__=cls,
                __config__=ConfigDict(
                    extra="forbid",
                    frozen=True,
                    populate_by_name=True,
                ),
                **field_definitions,
            )
        else:
            model = create_model(  # type: ignore[reportCallIssue, return-value]
                model_name,
                __base__=cls,
                **field_definitions,
            )
        if alias_specs:
            model.mcp_schema_alias_specs = alias_specs
            model.mcp_schema_alias_required = alias_required
        return model


class Action(Schema, ABC):
    """输入操作的基数模式。"""

    _structured_output: dict[str, Any] | None = PrivateAttr(default=None)

    @property
    def structured_output(self) -> dict[str, Any] | None:
        return self._structured_output

    @property
    def visualize(self) -> Text:
        """返回此操作的富文本表示形式。

        该方法可以被子类覆盖以定制可视化。 基本实现系统地显示所有操作字段。
        """
        content = Text()

        # 显示动作名称
        action_name = self.__class__.__name__
        content.append("Action: ", style="bold")
        content.append(action_name)
        content.append("\n\n")

        # 系统地显示所有操作字段
        content.append("Arguments:", style="bold")
        action_fields = self.model_dump()
        content.append(display_json(action_fields))

        return content


class Observation(Schema, ABC):
    """输出观测结果的基数模式。"""

    ERROR_MESSAGE_HEADER: ClassVar[str] = "[An error occurred during execution.]\n"

    content: list[TextContent | ImageContent] = Field(
        default_factory=list,
        description=(
            "Content returned from the tool as a list of "
            "TextContent/ImageContent objects. "
            "When there is an error, it should be written in this field."
        ),
    )
    is_error: bool = Field(
        default=False, description="Whether the observation indicates an error"
    )

    @classmethod
    def from_text(
        cls,
        text: str,
        is_error: bool = False,
        **kwargs: Any,
    ) -> "Self":
        """用于从简单文本字符串创建观测结果的实用程序。

        Args:
            text: 要包含在观测结果中的文本内容。
            is_error: 这个观测结果是否代表错误。
            **kwargs: 观测结果子类的附加字段。

        Returns:
            文本包含在 TextContent 中的观测结果实例。
        """
        return cls(content=[TextContent(text=text)], is_error=is_error, **kwargs)

    @property
    def text(self) -> str:
        """从观测结果中提取所有文本内容。

        Returns:
            内容中所有 TextContent 项的串联文本。
        """
        return "".join(
            item.text for item in self.content if isinstance(item, TextContent)
        )

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        """
        用于将观测结果转换为 LLM 可读内容的默认内容格式。 子类可以重写以提供更丰富的
        内容（e.g.、图像、差异）。
        """
        llm_content: list[TextContent | ImageContent] = []

        # 如果 is_error 为 True，则添加错误消息
        if self.is_error:
            llm_content.append(TextContent(text=self.ERROR_MESSAGE_HEADER))

        # 添加内容（现在始终是列表）
        llm_content.extend(self.content)

        return llm_content

    @property
    def visualize(self) -> Text:
        """返回此观测结果的富文本表示形式。

        子类可以覆盖自定义可视化； 默认情况下，我们显示将发送到 LLM 的相同文本。
        """
        text = Text()

        if self.is_error:
            text.append("❌ ", style="red bold")
            text.append(self.ERROR_MESSAGE_HEADER, style="bold red")

        text_parts = content_to_str(self.to_llm_content)
        if text_parts:
            full_content = "".join(text_parts)
            text.append(full_content)
        else:
            text.append("[no text content]")
        return text
