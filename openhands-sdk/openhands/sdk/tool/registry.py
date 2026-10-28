import inspect
from collections.abc import Callable, Sequence
from threading import RLock
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from openhands.sdk.logger import get_logger
from openhands.sdk.tool.spec import Tool
from openhands.sdk.tool.tool import ToolDefinition


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState

logger = get_logger(__name__)

# 解析器为给定参数生成 ToolDefinition 个实例。
Resolver = Callable[[dict[str, Any], "ConversationState"], Sequence[ToolDefinition]]
UsabilityChecker = Callable[[], bool]
"""解析器为给定参数生成 ToolDefinition 个实例。

Args:
    params: 传递给解析器的任意参数。 这些通常是
        用于配置创建的 ToolDefinition 个实例。
    conversation: 用于获取目录的可选对话状态。
Returns: ToolDefinition 实例的序列。 大多数时候这将是
    单项序列，但在某些情况下，ToolDefinition.create 可能会生成多个工具 (e.g.,
    BrowserToolSet)。
"""

_LOCK = RLock()
_REG: dict[str, Resolver] = {}
_USABILITY_REG: dict[str, UsabilityChecker] = {}
_TOOL_CLASSES: dict[str, type[ToolDefinition]] = {}
_SEALED_CATALOG: dict[str, tuple[type[ToolDefinition], UsabilityChecker]] | None = None


class ToolCatalogEntry(BaseModel):
    """为配置智能体的客户端提供的注册工具。"""

    name: str
    user_selectable: bool = True
    usable: bool = True
    description: str = ""
    in_default_set: bool = False
    """未设置 ``tools`` 的配置文件是否使该工具可用。"""


def _resolver_from_instance(name: str, tool: ToolDefinition) -> Resolver:
    if tool.executor is None:
        raise ValueError(
            "Unable to register tool: "
            f"ToolDefinition instance '{name}' must have a non-None .executor"
        )

    def _resolve(
        params: dict[str, Any], _conv_state: "ConversationState"
    ) -> Sequence[ToolDefinition]:
        if params:
            raise ValueError(
                f"ToolDefinition '{name}' is a fixed instance; params not supported"
            )
        return [tool]

    return _resolve


def _is_abstract_method(cls: type, name: str) -> bool:
    try:
        attr = inspect.getattr_static(cls, name)
    except AttributeError:
        return False
    # 解开类方法/静态方法
    if isinstance(attr, (classmethod, staticmethod)):
        attr = attr.__func__
    return bool(inspect.getattr_static(attr, "__isabstractmethod__", False))


def _resolver_from_subclass(_name: str, cls: type[ToolDefinition]) -> Resolver:
    try:
        create = cls.create
    except AttributeError:
        create = None

    if create is None or not callable(create) or _is_abstract_method(cls, "create"):
        raise TypeError(
            "Unable to register tool: "
            f"ToolDefinition subclass '{cls.__name__}' must define .create(**params)"
            f" as a concrete classmethod"
        )

    def _resolve(
        params: dict[str, Any], conv_state: "ConversationState"
    ) -> Sequence[ToolDefinition]:
        created = create(conv_state=conv_state, **params)
        if not isinstance(created, Sequence) or not all(
            isinstance(t, ToolDefinition) for t in created
        ):
            raise TypeError(
                f"ToolDefinition subclass '{cls.__name__}' create() must return "
                f"Sequence[ToolDefinition], "
                f"got {type(created)}"
            )
        # 可选的理智：允许没有执行者的工具； 他们会在 .call() 处失败
        return created

    return _resolve


def _usability_from_instance(tool: ToolDefinition) -> UsabilityChecker:
    return lambda: tool.__class__.is_usable()


def _usability_from_subclass(cls: type[ToolDefinition]) -> UsabilityChecker:
    return lambda: cls.is_usable()


def _check_tool_usable(name: str, checker: UsabilityChecker) -> bool:
    try:
        return checker()
    except Exception:
        logger.warning(
            "Failed to determine usability for tool '%s'", name, exc_info=True
        )
        return False


def register_tool(
    name: str,
    factory: ToolDefinition | type[ToolDefinition],
) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("ToolDefinition name must be a non-empty string")

    if isinstance(factory, ToolDefinition):
        resolver = _resolver_from_instance(name, factory)
        usability_checker = _usability_from_instance(factory)
    elif isinstance(factory, type) and issubclass(factory, ToolDefinition):
        resolver = _resolver_from_subclass(name, factory)
        usability_checker = _usability_from_subclass(factory)
    else:
        raise TypeError(
            "register_tool(...) only accepts: (1) a ToolDefinition instance with "
            ".executor, or (2) a ToolDefinition subclass with .create(**params)"
        )

    tool_class = factory if isinstance(factory, type) else factory.__class__

    with _LOCK:
        # TODO：注册重名工具时抛出异常
        if name in _REG:
            logger.warning(f"Duplicate tool name registered: {name}")
        _REG[name] = resolver
        _USABILITY_REG[name] = usability_checker
        _TOOL_CLASSES[name] = tool_class


def resolve_tool(
    tool_spec: Tool, conv_state: "ConversationState"
) -> Sequence[ToolDefinition]:
    with _LOCK:
        resolver = _REG.get(tool_spec.name)

    if resolver is None:
        from openhands.sdk.tool.builtins import builtin_tool_class

        tool_class = builtin_tool_class(tool_spec.name)
        if tool_class is None:
            raise KeyError(f"ToolDefinition '{tool_spec.name}' is not registered")
        resolver = _resolver_from_subclass(tool_spec.name, tool_class)

    params = dict(tool_spec.params)
    response_schema = params.pop("response_schema", None)
    tools = resolver(params, conv_state)
    if response_schema is not None:
        if len(tools) != 1:
            raise ValueError(
                "response_schema requires a spec that resolves to exactly one tool"
            )
        tools = [tools[0].set_response_schema(response_schema)]
    return tools


def list_registered_tools() -> list[str]:
    with _LOCK:
        return list(_REG.keys())


def is_tool_usable(name: str) -> bool:
    """``name`` 是否已注册 AND 其可用性检查是否通过。

    False 对于未注册的名称； 一个将计数提高为不可用的检查器（mirrors :func:
    `list_usable_tools`）。
    """
    with _LOCK:
        if name not in _REG:
            return False
        checker = _USABILITY_REG.get(name, lambda: True)
    return _check_tool_usable(name, checker)


def registered_tool_class(name: str) -> type[ToolDefinition] | None:
    """返回每个对话在 ``name`` 下注册的工具类。"""
    from openhands.sdk.tool.client_tool import ClientTool

    with _LOCK:
        tool_class = _TOOL_CLASSES.get(name)
    # 客户端工具属于注册它的会话。
    if tool_class is not None and issubclass(tool_class, ClientTool):
        return None
    return tool_class


def is_tool_available(name: str, *, check_usable: bool = True) -> bool:
    """``resolve_tool``是否解析``name``，如果选中，则可用。"""
    with _LOCK:
        checker = _USABILITY_REG.get(name, lambda: True) if name in _REG else None
    if checker is None:
        from openhands.sdk.tool.builtins import builtin_tool_class

        tool_class = builtin_tool_class(name)
        if tool_class is None:
            return False
        checker = _usability_from_subclass(tool_class)
    return not check_usable or _check_tool_usable(name, checker)


def list_usable_tools() -> list[str]:
    with _LOCK:
        tool_names = list(_REG.keys())
        usability_checkers = dict(_USABILITY_REG)

    return [
        name
        for name in tool_names
        if _check_tool_usable(name, usability_checkers.get(name, lambda: True))
    ]


def _registered_catalog() -> dict[str, tuple[type[ToolDefinition], UsabilityChecker]]:
    return {name: (_TOOL_CLASSES[name], _USABILITY_REG[name]) for name in _REG}


def seal_tool_catalog() -> None:
    """将目录冻结到迄今为止注册的工具。"""
    global _SEALED_CATALOG
    with _LOCK:
        _SEALED_CATALOG = _registered_catalog()


def unseal_tool_catalog() -> None:
    """让目录再次跟踪注册情况。"""
    global _SEALED_CATALOG
    with _LOCK:
        _SEALED_CATALOG = None


def list_tool_catalog(*, check_usable: bool = True) -> list[ToolCatalogEntry]:
    """列出用于配置智能体的工具，包括内置工具。

    ``check_usable=False`` 跳过可用性探测并报告每个可用的工具，对于其智能体运行在该进
    程无法探测的地方的调用者。
    """
    from openhands.sdk.tool.builtins import BUILT_IN_TOOL_CLASSES
    from openhands.sdk.tool.defaults import canonical_tool_name, resolve_tool_specs

    default_set = {
        canonical_tool_name(spec.name)
        for spec in resolve_tool_specs(None, enable_browser=True)
    }
    with _LOCK:
        registered = (
            dict(_SEALED_CATALOG)
            if _SEALED_CATALOG is not None
            else _registered_catalog()
        )
    # 在其类名下注册的内置函数在其工具名称下提供。
    offered = {
        canonical_tool_name(name): (name, tool_class, usability_checker)
        for name, (tool_class, usability_checker) in registered.items()
    }
    for tool_class in BUILT_IN_TOOL_CLASSES.values():
        if tool_class.user_selectable and tool_class.name not in offered:
            offered[tool_class.name] = (
                tool_class.name,
                tool_class,
                _usability_from_subclass(tool_class),
            )
    return [
        ToolCatalogEntry(
            name=name,
            user_selectable=tool_class.user_selectable,
            usable=not check_usable
            or _check_tool_usable(registered_name, usability_checker),
            description=tool_class.catalog_description,
            in_default_set=name in default_set,
        )
        for name, (registered_name, tool_class, usability_checker) in offered.items()
    ]


def get_tool_module_qualnames() -> dict[str, str]:
    """获取工具名称到其模块限定名的映射。

    Returns:
        将名称映射到模块限定名的字典工具 (e.g.,
        {"glob": "openhands.tools.glob.definition"}).
    """
    with _LOCK:
        return {
            name: tool_class.__module__ for name, tool_class in _TOOL_CLASSES.items()
        }
