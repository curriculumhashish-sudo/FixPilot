"""测试子类层次结构缓存。

models.py 中的生成计数器缓存通过 DiscriminatedUnionMixin.__init_subclass__ 自动失效。
 这些测试验证缓存在很容易损坏的情
况下是否正确：
  - 基本缓存命中
  - 新子类定义的自动失效（包括深层层次结构）
  - 动态 type() 调用自动失效（tool.py 的作用）
  - _get_checked_concrete_subclasses 保留在同步中并具有具体缓存
  - 并发多个线程的子类定义
"""

import threading
from abc import ABC

from openhands.sdk.utils.models import (
    DiscriminatedUnionMixin,
    _get_checked_concrete_subclasses,
    get_known_concrete_subclasses,
)


class _Base(DiscriminatedUnionMixin, ABC):
    pass


class _ConcreteA(_Base):
    x: int = 1


class _ConcreteB(_Base):
    x: int = 2


# _get_checked_concrete_subclasses 测试的单独层次结构（拒绝 <locals> 类）。
#
class _CheckedBase(DiscriminatedUnionMixin, ABC):
    pass


class _CheckedA(_CheckedBase):
    x: int = 1


def test_cache_hit():
    """连续调用返回完全相同的元组对象。"""
    first = get_known_concrete_subclasses(_Base)
    second = get_known_concrete_subclasses(_Base)
    assert first is second


def test_returns_tuple():
    """缓存的结果是一个元组（不可变）。"""
    assert isinstance(get_known_concrete_subclasses(_Base), tuple)


def test_auto_invalidates_on_new_subclass():
    """定义一个新的直接子类会使父类的缓存失效。"""
    first = get_known_concrete_subclasses(_Base)

    class _ConcreteNew(_Base):
        x: int = 99

    second = get_known_concrete_subclasses(_Base)
    assert first is not second
    assert _ConcreteNew in second


def test_deep_hierarchy_invalidation():
    """子类的子类仍然会使根祖先的缓存无效。"""

    class _Mid(_Base, ABC):
        pass

    class _Leaf(_Mid):
        x: int = 42

    result = get_known_concrete_subclasses(_Base)
    assert _Leaf in result

    # 现在添加更深的叶子 - _Base 缓存必须看到它。
    class _Leaf2(_Mid):
        x: int = 43

    result2 = get_known_concrete_subclasses(_Base)
    assert result2 is not result
    assert _Leaf2 in result2


def test_dynamic_type_invalidates_cache():
    """type() 调用（tool.py 使用的内容）触发 __init_subclass__。"""
    before = get_known_concrete_subclasses(_Base)

    DynClass = type("_DynSubclass", (_Base,), {"__annotations__": {"x": int}})

    after = get_known_concrete_subclasses(_Base)
    assert after is not before
    assert DynClass in after


def test_checked_cache_stays_in_sync():
    """_get_checked_concrete_subclasses 与具体缓存一起失效。"""
    checked_before = _get_checked_concrete_subclasses(_CheckedBase)
    assert "_CheckedA" in checked_before

    # 动态添加模块级子类，因此 qualname 没有 <locals>。
    cls = type("_CheckedB", (_CheckedBase,), {"__annotations__": {"x": int}})
    cls.__module__ = __name__
    cls.__qualname__ = "_CheckedB"

    checked_after = _get_checked_concrete_subclasses(_CheckedBase)
    assert checked_after is not checked_before
    assert "_CheckedB" in checked_after


def test_concurrent_subclass_creation():
    """多个线程定义子类 — 全部完成后缓存是正确的。"""

    class _ThreadBase(_Base, ABC):
        pass

    barrier = threading.Barrier(8)
    created: list[type] = []
    lock = threading.Lock()

    def worker(idx: int) -> None:
        barrier.wait()
        cls = type(
            f"_Thread{idx}",
            (_ThreadBase,),
            {"__annotations__": {"x": int}, "x": idx},
        )
        with lock:
            created.append(cls)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = get_known_concrete_subclasses(_ThreadBase)
    for cls in created:
        assert cls in result, f"{cls.__name__} missing from cache result"
