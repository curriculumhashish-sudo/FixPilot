"""回归测试禁止的动态属性预提交挂钩。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "check_forbidden_dynamic_attributes.py"
)


def _load_module(tmp_path: Path) -> Any:
    """将检查器脚本加载为具有隔离基线的可导入模块。"""
    spec = importlib.util.spec_from_file_location("checker", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 在 exec 之后重写，这样模块级分配就不会破坏它。
    module.BASELINE_FILE = tmp_path / "baseline.json"  # type: ignore[attr-defined]
    return module


@pytest.fixture()
def checker(tmp_path: Path):
    return _load_module(tmp_path)


def _write_py(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def test_clean_file_passes(checker, tmp_path: Path):
    """没有禁止调用的文件不会产生违规。"""
    f = _write_py(tmp_path / "clean.py", "x = 1\n")
    assert checker.main([str(f)]) == 0


def test_new_violation_fails(checker, tmp_path: Path):
    """不在基线中的 getattr 调用将被拒绝。"""
    f = _write_py(tmp_path / "bad.py", 'v = getattr(obj, "attr")\n')
    assert checker.main([str(f)]) == 1


def test_baselined_violation_passes(checker, tmp_path: Path):
    """接受基线中存在的 getattr 调用。"""
    f = _write_py(tmp_path / "ok.py", 'v = getattr(obj, "attr")\n')
    checker.main([str(f), "--update-baseline"])
    assert checker.main([str(f)]) == 0


def test_duplicate_baselined_line_is_rejected(checker, tmp_path: Path):
    """复制已经设置基线的源代码行仍然会失败。

    这是密钥回归：a *set*-基于比较会接受第二个相同的行，但一个集合（Counter）比较会正
    确拒绝它，因为当前计数超过了基线计数。
    """
    f = _write_py(tmp_path / "dup.py", 'v = getattr(obj, "attr")\n')
    checker.main([str(f), "--update-baseline"])  # 基线现在计数为 1

    # 在不同的行号上添加第二个相同的行。
    _write_py(f, 'v = getattr(obj, "attr")\nw = getattr(obj, "attr")\n')
    assert checker.main([str(f)]) == 1


def test_stale_baseline_entry_fails(checker, tmp_path: Path):
    """删除基线调用会使其基线条目过时，从而失败。

    过时的条目必须失败（而不仅仅是打印注释），因此删除呼叫会永久缩小限额，而不是留下
    可重复使用的插槽。
    """
    f = _write_py(tmp_path / "stale.py", 'v = getattr(obj, "attr")\n')
    checker.main([str(f), "--update-baseline"])

    # 删除通话； 基线仍然记录它。
    _write_py(f, "v = 1\n")
    assert checker.main([str(f)]) == 1


def test_remove_then_reintroduce_is_caught(checker, tmp_path: Path):
    """重新引入已删除的调用必定会失败。

    基线一 ``getattr``，将其替换为 ``x.y``（检查过时条目失败，强制基线刷新），然后恢
    复相同的行。 由于过时的条目强制刷新，因此重新引入的调用不再被覆
    盖并被正确拒绝。
    """
    f = _write_py(tmp_path / "reintro.py", 'v = getattr(obj, "attr")\n')
    checker.main([str(f), "--update-baseline"])  # 基线计数 = 1

    # 删除调用→陈旧条目→必须失败。
    _write_py(f, "v = obj.attr\n")
    assert checker.main([str(f)]) == 1
    # 开发人员被迫刷新基线，现在记录为 0。
    checker.main([str(f), "--update-baseline"])

    # 重新引入相同的调用 → 现在是 *new* 违规，未涵盖。
    _write_py(f, 'v = getattr(obj, "attr")\n')
    assert checker.main([str(f)]) == 1


def test_update_baseline_idempotent(checker, tmp_path: Path):
    """运行 --update-baseline 两次会生成相同的文件。"""
    f = _write_py(tmp_path / "idem.py", 'v = getattr(obj, "attr")\n')
    checker.main([str(f), "--update-baseline"])
    first = json.loads(checker.BASELINE_FILE.read_text())
    checker.main([str(f), "--update-baseline"])
    second = json.loads(checker.BASELINE_FILE.read_text())
    assert first == second


def test_setattr_also_detected(checker, tmp_path: Path):
    """setattr 也被禁止。"""
    f = _write_py(tmp_path / "set.py", 'setattr(obj, "attr", 1)\n')
    assert checker.main([str(f)]) == 1


def test_dunder_dict_get_also_detected(checker, tmp_path: Path):
    """直接实例字典查找也是被禁止的。"""
    f = _write_py(tmp_path / "dict_get.py", 'value = obj.__dict__.get("attr")\n')

    assert checker.main([str(f)]) == 1


def test_regular_dict_get_is_allowed(checker, tmp_path: Path):
    """普通映射访问不是动态属性访问。"""
    f = _write_py(tmp_path / "dict_get.py", 'value = data.get("key")\n')

    assert checker.main([str(f)]) == 0


def test_deleted_baselined_file_is_stale(checker, tmp_path: Path):
    """即使在检查其他文件时也必须捕获删除基线文件。

    在预提交阶段，检查器不能将已删除的文件传递给钩子，因此必须标记文件已不存在的基线
    条目——即使当前运行检查的是一个不同的（仍然存在的）文件。
    """
    f = _write_py(tmp_path / "deleted.py", 'v = getattr(obj, "attr")\n')
    checker.main([str(f), "--update-baseline"])

    f.unlink()  # 模拟删除

    other = _write_py(tmp_path / "other.py", "x = 1\n")
    assert checker.main([str(other)]) == 1


def test_multiline_arg_change_is_caught(checker, tmp_path: Path):
    """在多行调用的后续行上编辑参数必须失败。

    因为基线会计算完整的调用源段（而不是只计算第一行物理行），在第一行之后更改参数会
    产生不同的哈希值，并且正确地被拒绝为新的违规行为。
    """
    original = "v = getattr(\n    obj,\n    'attr',\n)\n"
    f = _write_py(tmp_path / "multiline.py", original)
    checker.main([str(f), "--update-baseline"])

    # 更改后续行的参数 - 相同的第一行，不同的调用。
    _write_py(f, "v = getattr(\n    obj,\n    'other',\n)\n")
    assert checker.main([str(f)]) == 1


def test_baseline_addition_is_rejected(checker):
    """基线可能永远不会获得新的津贴。"""
    reference = checker.Counter({("a.py", "getattr", "old"): 1})
    current = checker.Counter(
        {
            ("a.py", "getattr", "old"): 1,
            ("b.py", "setattr", "new"): 1,
        }
    )

    assert checker._baseline_additions(reference, current) == checker.Counter(
        {("b.py", "setattr", "new"): 1}
    )


def test_baseline_removal_is_allowed(checker):
    """删除现有配额可保持基线单调性。"""
    reference = checker.Counter(
        {
            ("a.py", "getattr", "old"): 1,
            ("b.py", "setattr", "removed"): 1,
        }
    )
    current = checker.Counter({("a.py", "getattr", "old"): 1})

    assert not checker._baseline_additions(reference, current)


def test_duplicate_baseline_addition_is_rejected(checker):
    """增加现有津贴的多样性也是一种补充。"""
    key = ("a.py", "getattr", "same")

    assert checker._baseline_additions(
        checker.Counter({key: 1}), checker.Counter({key: 2})
    ) == checker.Counter({key: 1})


def test_baseline_ref_option_rejects_addition(checker, tmp_path: Path, monkeypatch):
    """CLI 防护在接受扩展基线之前失败。"""
    key = ("added.py", "getattr", "new")
    checker.BASELINE_FILE.write_text(
        json.dumps([{"file": key[0], "name": key[1], "hash": key[2]}])
    )
    monkeypatch.setattr(
        checker, "_load_baseline_from_git", lambda _ref: checker.Counter()
    )
    clean = _write_py(tmp_path / "clean.py", "x = 1\n")

    assert checker.main([str(clean), "--baseline-ref", "base-sha"]) == 1


def test_baseline_ref_option_allows_removal(checker, tmp_path: Path, monkeypatch):
    """CLI 保护允许作为严格子集的基线。"""
    removed = ("removed.py", "getattr", "old")
    checker.BASELINE_FILE.write_text("[]\n")
    monkeypatch.setattr(
        checker,
        "_load_baseline_from_git",
        lambda _ref: checker.Counter({removed: 1}),
    )
    clean = _write_py(tmp_path / "clean.py", "x = 1\n")

    assert checker.main([str(clean), "--baseline-ref", "base-sha"]) == 0
