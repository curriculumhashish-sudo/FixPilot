import inspect
import logging
import threading
from abc import ABC
from typing import Annotated, Any, Self, Union

from pydantic import (
    BaseModel,
    Discriminator,
    ModelWrapValidatorHandler,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    Tag,
    ValidationInfo,
    computed_field,
    model_serializer,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema


logger = logging.getLogger(__name__)

# 线程局部当前正在生成的用于跟踪模式的存储。 这可以防止在为相互引用的可区分联合生成 JSON
#  模式时出现无限递归。
#
_thread_local = threading.local()


def _get_schemas_in_progress() -> dict[type, JsonSchemaValue]:
    """获取用于跟踪正在进行的模式生成的线程局部字典。"""
    if not hasattr(_thread_local, "schemas_in_progress"):
        _thread_local.schemas_in_progress = {}
    return _thread_local.schemas_in_progress


def _is_abstract(type_: type) -> bool:
    """判断类是否直接扩展ABC或包含抽象方法"""
    try:
        return inspect.isabstract(type_) or ABC in type_.__bases__
    except Exception:
        return False


def _is_object_input(data: Any, cls: type) -> bool:
    """``data`` 是字典还是 ``cls`` 的实例（布尔值，因此
    Pyright 不会在调用站点缩小 ``data``）。"""
    return isinstance(data, (dict, cls))


def get_handler_class_name(handler: SerializerFunctionWrapHandler) -> str:
    """从 Pydantic 序列化器处理程序的 repr 字符串中提取类名。

    WARNING: 这是一种脆弱的方法，依赖于 Pydantic 的内部
    SerializerFunctionWrapHandler 的 repr 格式。 该处理程序是 Rust 函数的 Pydantic 包
    装器，不提供公共 API 来确
    定它序列化哪个类。 解析 repr 字符串是唯一可用的机制。

    预期格式：`SerializationCallable(serializer=<ClassName>)`

    如果 Pydantic 更改此格式，多个单元测试将立即失败，包括
    test_discriminated_union.py 中验证整个类层次结构中的序列化行为的测试。

    Args:
        handler: Pydantic 序列化器函数包装处理程序

    Returns:
        从处理程序的 repr 字符串中提取的类名
    """
    repr_str = str(handler)
    # 格式为 `SerializationCallable(serializer=<NAME>)` 获取 = 之后的所有内容
    #
    _, name = repr_str.split("=", 1)
    # 剪掉尾部）
    return name[:-1]


def kind_of(obj) -> str:
    """获取种类标签的字符串值"""
    if isinstance(obj, dict):
        return obj["kind"]
    if not hasattr(obj, "__name__"):
        obj = obj.__class__
    return obj.__name__


def _get_all_subclasses(cls) -> set[type]:
    """
    递归查找并返回给定类的所有（已加载）子类。
    """
    result = set()
    for subclass in cls.__subclasses__():
        result.add(subclass)
        result.update(_get_all_subclasses(subclass))
    return result


# ---------------------------------------------------------------------------
# 子类层次结构缓存
#
# get_known_concrete_subclasses() 和 _get_checked_concrete_subclasses() 在每个事件反序列
# 化上调用（通过 _validate_subtype）。 每次遍历完整的类层次结构都占主导地位CPU（约占墙轮
# 廓中自时间的 47%）。
#
# 缓存以 (cls, _subclass_generation) 为键。 每次定义一个新的子类时，生成器计数器都会自动
# 增加 DiscriminatedUnionMixin.__init_subclass__，因此调用者无需手动 invalidate — 缓存会
# 自动失效。
# ---------------------------------------------------------------------------
_subclass_generation: int = 0
_subclass_generation_lock = threading.Lock()
_concrete_cache: dict[type, tuple[int, tuple[type, ...]]] = {}
_checked_cache: dict[type, tuple[int, dict[str, type]]] = {}


def _bump_subclass_generation() -> None:
    global _subclass_generation
    with _subclass_generation_lock:
        _subclass_generation += 1


def get_known_concrete_subclasses(cls) -> tuple[type, ...]:
    """以稳定的顺序递归返回所有具体子类，
    无需对共享相同（模块、名称）的类进行重复数据删除。

    当定义新的 DiscriminatedUnionMixin 子类时，结果将被缓存并自动失效。
    """
    cached = _concrete_cache.get(cls)
    if cached is not None and cached[0] == _subclass_generation:
        return cached[1]

    out: list[type] = []
    for sub in cls.__subclasses__():
        # 首先递归，以便更深的类在其父母之后出现
        out.extend(get_known_concrete_subclasses(sub))
        if not _is_abstract(sub):
            out.append(sub)

    # 使用 qualname 来区分嵌套/本地类（如 test-local Cat）
    out.sort(key=lambda t: (t.__module__, getattr(t, "__qualname__", t.__name__)))
    result = tuple(out)
    _concrete_cache[cls] = (_subclass_generation, result)
    return result


def _get_checked_concrete_subclasses(cls: type) -> dict[str, type]:
    cached = _checked_cache.get(cls)
    if cached is not None and cached[0] == _subclass_generation:
        return cached[1]

    result: dict[str, type] = {}
    for sub in get_known_concrete_subclasses(cls):
        existing = result.get(sub.__name__)
        if existing:
            raise ValueError(
                f"Duplicate class definition for {cls.__module__}.{cls.__name__}: "
                f"{existing.__module__}.{existing.__name__} : "
                f"{sub.__module__}.{sub.__name__}"
            )
        if "<locals>" in sub.__qualname__:
            raise ValueError(
                f"Local classes not supported! {sub.__module__}.{sub.__name__} "
                f"/ {cls.__module__}.{cls.__name__} "
                "(Since they may not exist at deserialization time)"
            )
        result[sub.__name__] = sub
    _checked_cache[cls] = (_subclass_generation, result)
    return result


def clear_subclass_cache() -> None:
    """使：func:`get_known_concrete_subclasses` 的缓存结果无效
    和：func:`_get_checked_concrete_subclasses`。

    通常不需要 — 当定义新的 DiscriminatedUnionMixin 子类时，缓存自动失效。 此函数适用
    于涉及非
    DiscriminatedUnionMixin 层次结构的边缘情况。

    条目被删除，而不仅仅是被取代：陈旧的条目是对其捕获的每个子类的强引用。
    """
    _concrete_cache.clear()
    _checked_cache.clear()
    _bump_subclass_generation()


class OpenHandsModel(BaseModel):
    """Deprecated: 该类仅针对向后兼容性存在。

    受歧视的工会支持不再需要此类。 新代码应该直接扩展pydantic.BaseModel而不是
    OpenHandsModel。

    扩展 OpenHandsModel 的现有代码将继续工作，但建议迁移到 BaseModel。
    """


class DiscriminatedUnionMixin(OpenHandsModel):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _bump_subclass_generation()

    @computed_field
    @property
    def kind(self) -> str:
        return self.__class__.__name__

    @model_validator(mode="wrap")
    @classmethod
    def _validate_subtype(
        cls, data: Any, handler: ModelWrapValidatorHandler[Self], info: ValidationInfo
    ) -> Self:
        if not _is_object_input(data, cls):
            # 让 Pydantic 将非对象输入（字符串、数字、null、列表...）报告为
            # ValidationError，而不是在 .pop() 上失败。
            #
            return handler(data)
        if isinstance(data, cls):
            return data
        if isinstance(data, dict):
            # 永远不要改变调用者的字典：诸如 RemoteState 之类的调用者多次验证相同的缓存
            # 载荷。
            #
            data = dict(data)
        if not _is_abstract(cls):
            has_kind_alias_field = any(
                field_name != "kind" and field_info.alias == "kind"
                for field_name, field_info in cls.model_fields.items()
            )
            if has_kind_alias_field:
                # 具体的已持久化转储可以包括真实的别名参数和该 mixin 的计算鉴别器。
                #
                if isinstance(data, dict) and data.get("kind") == cls.__name__:
                    internal_kind_field = next(
                        (
                            field_name
                            for field_name, field_info in cls.model_fields.items()
                            if field_name != "kind" and field_info.alias == "kind"
                        ),
                        None,
                    )
                    if internal_kind_field in data:
                        data.pop("kind", None)
                return handler(data)
            kind = data.pop("kind", None)
            # 健全性检查：如果我们直接验证具体类，则类型（如果提供）应与类名匹配。 此时
            # 应该始终为 True，因为 resolve_kind() 已经路由到正确的子类。
            #
            assert kind is None or kind == cls.__name__
            return handler(data)
        kind = data.pop("kind", None)
        if kind is None:
            subclasses = _get_checked_concrete_subclasses(cls)
            if not subclasses:
                raise ValueError(
                    f"No kinds defined for {cls.__module__}.{cls.__name__}"
                )
            elif len(subclasses) == 1:
                # 如果只有 1 种可能的实现，那么我们不需要显式地声明类型 - 只能是这个！
                #
                kind = next(iter(subclasses))
            else:
                # 定义了超过 1 种，但输入未指定这将导致引发错误
                #
                kind = ""
        subclass = cls.resolve_kind(kind)
        return subclass.model_validate(data, context=info.context)

    @model_serializer(mode="wrap")
    def _serialize_by_kind(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ):
        if isinstance(self, dict):
            # 有时 Pydantic 在这里传递一个字典。
            return self
        if self._is_handler_for_current_class(handler):
            result = handler(self)
            return result

        # 委托给实现类
        result = self.model_dump(
            mode=info.mode,
            context=info.context,
            by_alias=info.by_alias,
            exclude_unset=info.exclude_unset,
            exclude_defaults=info.exclude_defaults,
            exclude_none=info.exclude_none,
            exclude_computed_fields=info.exclude_computed_fields,
            round_trip=info.round_trip,
            serialize_as_any=info.serialize_as_any,
        )
        return result

    def _is_handler_for_current_class(
        self, handler: SerializerFunctionWrapHandler
    ) -> bool:
        """检查处理程序是否适用于此类。

        有关解析所依赖的脆弱字符串的详细信息，请参阅 get_handler_class_name()。
        """
        return self.__class__.__name__ == get_handler_class_name(handler)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: Any
    ) -> JsonSchemaValue:
        schemas_in_progress = _get_schemas_in_progress()

        # 首先我们检查是否已经生成了模式
        schema = schemas_in_progress.get(cls)
        if schema:
            return schema

        # 设置温度模式以防止无限递归
        schemas_in_progress[cls] = {"$ref": f"#/$defs/{cls.__name__}"}
        try:
            if _is_abstract(cls):
                subclasses = _get_checked_concrete_subclasses(cls)
                if not subclasses:
                    raise ValueError(f"No subclasses defined for {cls.__name__}")
                if len(subclasses) == 1:
                    # 也对单个子类使用共享生成器
                    gen = handler.generate_json_schema
                    sub_schema = gen.generate_inner(
                        next(iter(subclasses.values())).__pydantic_core_schema__
                    )
                    return sub_schema

                # 使用共享生成器正确注册定义
                gen = handler.generate_json_schema
                schemas = []
                for sub in subclasses.values():
                    sub_schema = gen.generate_inner(sub.__pydantic_core_schema__)
                    schemas.append(sub_schema)

                # 从 $ref 模式构建鉴别器映射
                mapping = {}
                for option in schemas:
                    if "$ref" in option:
                        kind = option["$ref"].split("/")[-1]
                        mapping[kind] = option["$ref"]

                schema = {
                    "oneOf": schemas,
                    "discriminator": {"propertyName": "kind", "mapping": mapping},
                }
            else:
                schema = handler(core_schema)
                schema["properties"]["kind"] = {
                    "const": cls.__name__,
                    "title": "Kind",
                    "type": "string",
                }
        finally:
            # 重置温度模式
            schemas_in_progress.pop(cls)
        return schema

    @classmethod
    def resolve_kind(cls, kind: str) -> type[Self]:
        subclasses = _get_checked_concrete_subclasses(cls)
        subclass = subclasses.get(kind)
        if subclass:
            return subclass
        raise ValueError(
            f"Unknown kind '{kind}' for {cls.__module__}.{cls.__name__}; "
            f"Expected one of: {list(subclasses)}"
        )

    @classmethod
    def get_serializable_type(cls) -> type:
        """
        获取所有当前加载的非抽象子类的并集的自定义方法
        """

        # 如果类不是抽象类，则返回 self
        if not _is_abstract(cls):
            return cls

        subclasses = _get_checked_concrete_subclasses(cls)
        if not subclasses:
            return cls

        if len(subclasses) == 1:
            # 返回具体类型可确保 Pydantic 实例化子类 (e.g. 智能体) 而不是抽象基础 (e.g.
            # AgentBase) 当只有一个个具体子类时。
            #
            return next(iter(subclasses.values()))

        serializable_type = Annotated[
            Union[*tuple(Annotated[t, Tag(n)] for n, t in subclasses.items())],
            Discriminator(kind_of),
        ]
        return serializable_type  # type: ignore
