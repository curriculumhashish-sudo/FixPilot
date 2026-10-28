"""事件或观测结果上的每个 id 字段都必须选择退出机密屏蔽。

输入新的 id 字段作为 ``EventID``、``ToolCallID`` 或 ``UnmaskedID``
``openhands.sdk.event.types``.
"""

import importlib
import pkgutil
from typing import get_args

from pydantic import BaseModel

from openhands.sdk.conversation.secret_registry import SecretRegistry
from openhands.sdk.event import Event
from openhands.sdk.tool import Observation
from openhands.sdk.utils.masking import SkipSecretMasking, field_has_marker
from openhands.tools.child_conversation.definition import (
    StartChildConversationObservation,
)
from openhands.tools.task.definition import TaskObservation


SECRET = "a1b"
MASK = "<secret-hidden>"
ID = "fa1b4e36-bdd7-42bf-99df-e184c9dc0d9a"

# “Class.field”真正可以容纳机密的id字段的名称。
_ALLOWLIST: set[str] = set()


def _registry() -> SecretRegistry:
    registry = SecretRegistry()
    registry.update_secrets({"SHORT": SECRET})
    registry.get_secret_value("SHORT")  # 解析 -> 跟踪掩码
    return registry


def _is_id_name(name: str) -> bool:
    return name == "id" or name.endswith(("_id", "_ids"))


def _can_hold_str(annotation: object) -> bool:
    # ``list[int]`` token id 永远不会被屏蔽，因此它们不需要标记。
    return annotation is str or any(_can_hold_str(a) for a in get_args(annotation))


def _unmarked_id_fields(cls: type[BaseModel]) -> list[str]:
    """返回机密屏蔽将重写的 ``cls`` 的 id 字段。"""
    return [
        f"{cls.__qualname__}.{name}"
        for name, field in cls.model_fields.items()
        if _is_id_name(name)
        and _can_hold_str(field.annotation)
        and not field_has_marker(field, SkipSecretMasking)
    ]


def _all_subclasses(*bases: type[BaseModel]) -> set[type[BaseModel]]:
    """导入每个已发布的 SDK 和工具模块，然后收集子类。"""
    import openhands.sdk
    import openhands.tools

    for package in (openhands.sdk, openhands.tools):
        for module in pkgutil.walk_packages(
            package.__path__, prefix=f"{package.__name__}."
        ):
            try:
                importlib.import_module(module.name)
            except Exception:  # 可选的附加设施不能让警卫失望
                continue

    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    return {cls for base in bases for cls in (base, *walk(base))}


def test_every_event_and_observation_id_field_skips_masking():
    offenders = sorted(
        name
        for cls in _all_subclasses(Event, Observation)
        if cls.__module__.startswith("openhands.")
        for name in _unmarked_id_fields(cls)
        if name not in _ALLOWLIST
    )

    assert not offenders, (
        "These id fields are secret-masked, so a secret inside the id rewrites "
        "it. Type them as EventID, ToolCallID or UnmaskedID: "
        f"{offenders}"
    )


def test_guard_flags_an_unmarked_id_field():
    class _NewEvent(Event):
        foo_id: str
        bar_ids: list[str] | None = None

    assert _unmarked_id_fields(_NewEvent) == [
        "test_guard_flags_an_unmarked_id_field.<locals>._NewEvent.foo_id",
        "test_guard_flags_an_unmarked_id_field.<locals>._NewEvent.bar_ids",
    ]


def test_tool_observation_ids_are_not_masked():
    child = StartChildConversationObservation.from_text(
        f"started {SECRET}", conversation_id=ID, parent_conversation_id=ID
    )
    task = TaskObservation.from_text(
        f"done {SECRET}", task_id=ID, subagent="sub", status="completed"
    )

    masked_child = _registry().mask_secrets_in_model(child)
    masked_task = _registry().mask_secrets_in_model(task)

    assert masked_child.conversation_id == ID
    assert masked_child.parent_conversation_id == ID
    assert masked_child.text == f"started {MASK}"
    assert masked_task.task_id == ID
    assert masked_task.text == f"done {MASK}"
