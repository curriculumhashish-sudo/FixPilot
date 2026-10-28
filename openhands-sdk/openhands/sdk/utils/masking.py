"""机密屏蔽使用的字段元数据。"""

from collections.abc import Mapping
from typing import Annotated, Any, get_args, get_origin

from pydantic.fields import FieldInfo


class SkipSecretMasking:
    """标记其值不能被机密屏蔽的字段。"""

    __slots__ = ()


class PreserveDataUrls:
    """标记包含纯基64数据的字符串值 URLs。"""

    __slots__ = ()


def field_has_marker(field: FieldInfo, marker: type) -> bool:
    """返回 ``marker`` 是否注释 ``field`` 或其类型的一部分。

    Pydantic 将 ``Annotated`` 元数据移动到 ``field.metadata`` 仅用于裸露
    ``Annotated[...]``. 对于 ``EventID | None`` 或 ``set[EventID]``，标记保留在
    ``field.annotation`` 中，因此这也会遍历类型参数。 仅当每个参数都带有标记时，泛型
    类型才算数，因此 id (
    ``EventID | list[str]``) 旁边的文本仍然被屏蔽。
    """
    return any(isinstance(item, marker) for item in field.metadata) or (
        _type_has_marker(field.annotation, marker)
    )


def _type_has_marker(annotation: Any, marker: type) -> bool:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Annotated:
        base, *metadata = args
        return any(isinstance(item, marker) for item in metadata) or (
            _type_has_marker(base, marker)
        )
    if isinstance(origin, type) and issubclass(origin, Mapping):
        # 屏蔽永远不会触及字典键，因此只有值类型才重要。
        args = args[1:]
    args = tuple(arg for arg in args if arg not in (type(None), Ellipsis))
    return bool(args) and all(_type_has_marker(arg, marker) for arg in args)
