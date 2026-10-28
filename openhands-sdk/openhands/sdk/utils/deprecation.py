from __future__ import annotations

import warnings
from collections.abc import Callable
from datetime import date
from functools import cache
from importlib.metadata import PackageNotFoundError, version as get_version
from typing import Any, TypeVar, cast

from deprecation import (
    DeprecatedWarning,
    UnsupportedWarning,
    deprecated as _deprecated,
)
from packaging import version as pkg_version


_FuncT = TypeVar("_FuncT", bound=Callable[..., Any])


@cache
def _current_version() -> str:
    try:
        return get_version("openhands-sdk")
    except PackageNotFoundError:
        return "0.0.0"


def deprecated(
    *,
    deprecated_in: str,
    removed_in: str | date | None,
    current_version: str | None = None,
    details: str = "",
) -> Callable[[_FuncT], _FuncT]:
    """返回一个装饰器，该装饰器不赞成使用显式元数据的可调用对象。

    当您可以使用以下方式注释函数、方法或属性时，请使用此帮助器
    `@deprecated(...)`. 它透明地转发到：func:`deprecation.deprecated`
    while filling in the SDK's current version metadata unless custom values are
    提供。
    """

    base_decorator = _deprecated(
        deprecated_in=deprecated_in,
        removed_in=removed_in,
        current_version=current_version or _current_version(),
        details=details,
    )

    def decorator(func: _FuncT) -> _FuncT:
        return cast(_FuncT, base_decorator(func))

    return decorator


def _should_warn(
    *,
    deprecated_in: str | None,
    removed_in: str | date | None,
    current_version: str | None,
) -> tuple[bool, bool]:
    is_deprecated = False
    is_unsupported = False

    if isinstance(removed_in, date):
        if date.today() >= removed_in:
            is_unsupported = True
        else:
            is_deprecated = True
    elif current_version:
        current = pkg_version.parse(current_version)
        if removed_in and current >= pkg_version.parse(str(removed_in)):
            is_unsupported = True
        elif deprecated_in and current >= pkg_version.parse(deprecated_in):
            is_deprecated = True
    else:
        is_deprecated = True

    return is_deprecated, is_unsupported


def warn_deprecated(
    feature: str,
    *,
    deprecated_in: str,
    removed_in: str | date | None,
    current_version: str | None = None,
    details: str = "",
    stacklevel: int = 2,
) -> None:
    """针对动态访问旧功能发出弃用警告。

    当装饰器不实用时更喜欢这个助手 - e.g。 属性访问器、数据迁移或其他必须有条件发出警
    告的运行时路径。 提供显式版本元数据，以便 SDK 报告一致的消息并在删除阈
    值后升级到：class:`deprecation.UnsupportedWarning`。
    """

    current_version = current_version or _current_version()
    is_deprecated, is_unsupported = _should_warn(
        deprecated_in=deprecated_in,
        removed_in=removed_in,
        current_version=current_version,
    )

    if not (is_deprecated or is_unsupported):
        return

    warning_cls = UnsupportedWarning if is_unsupported else DeprecatedWarning
    warning = warning_cls(feature, deprecated_in, removed_in, details)
    warnings.warn(warning, stacklevel=stacklevel)


def warn_cleanup(
    workaround: str,
    *,
    cleanup_by: str | date,
    current_version: str | None = None,
    details: str = "",
    stacklevel: int = 2,
) -> None:
    """对需要在截止日期前清理的临时解决方法发出警告。

    请使用此辅助程序编写临时代码，用于解决上游问题、兼容性补丁或其他工作绕道，
    这些工作绕道应在外部条件改变后移除(e.g，当一个库添加对一个功能的支持，或当一个API
    稳定化)。 当达到清理截止时间时，弃用检查工作流程将失败，确保在指定版本或日
    期之前删除解决方法。

    Args:
        workaround: 临时解决方法的说明
        cleanup_by: 必须删除此解决方法的版本字符串或日期
        current_version: 覆盖检测到的包版本（用于测试）
        details: 关于为什么需要清理的附加上下文
        stacklevel: 警告排放的堆栈级别
    """
    current_version = current_version or _current_version()

    should_cleanup = False
    if isinstance(cleanup_by, date):
        should_cleanup = date.today() >= cleanup_by
    else:
        try:
            current = pkg_version.parse(current_version)
            target = pkg_version.parse(str(cleanup_by))
            should_cleanup = current >= target
        except pkg_version.InvalidVersion:
            pass

    if should_cleanup:
        message = (
            f"Cleanup required: {workaround}. "
            f"This workaround was scheduled for removal by {cleanup_by}."
        )
        if details:
            message += f" {details}"
        warnings.warn(message, UserWarning, stacklevel=stacklevel)


def handle_deprecated_model_fields(
    data: Any,
    deprecated_fields: tuple[str, ...],
) -> Any:
    """从 Pydantic 模型输入数据中删除已弃用字段。

    此函数会默默地从输入数据中删除已弃用字段，以便带有 extra="forbid" 的 Pydantic 模
    型不会拒绝它们。 这用于加载旧已序列化数据时的永久向后兼容
    性（e.g.、事件
    from older SDK versions).

    与 warn_deprecated() 不同，此函数不会发出警告，因为这些字段会永久保留向后兼容性并
    且永远不会被删除。 这确保了旧的对话和事件始终可以毫无错误地加载
    。

    Args:
        data: 输入数据（通常是来自反序列化的字典）
        deprecated_fields: 字段名称元组为已弃用

    Returns:
        删除已弃用字段的数据

    Example:
        class MyModel(BaseModel):
            model_config = ConfigDict(extra="forbid")

            @model_validator(mode="before")
            @classmethod
            def _handle_deprecated(cls, data: Any) -> Any:
                返回handle_deprecated_model_fields(
                    数据，（“old_field”，“another_old_field”）
                )
    """  # noqa: E501
    if not isinstance(data, dict):
        return data

    for field in deprecated_fields:
        data.pop(field, None)

    return data


__all__ = [
    "deprecated",
    "warn_deprecated",
    "warn_cleanup",
    "handle_deprecated_model_fields",
]
