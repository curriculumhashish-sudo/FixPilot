"""测试供应链依赖性差异发布检查。

测试纯源分类辅助函数 —— 决定一个已解析依赖是否可信（PyPI / 第三方）或必须阻止发布（镜
像、替代索引、git/URL 或未识别的形状）。 否
network: 这里从未触及 OSV 和 GitHub。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(name: str):
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / ".github" / "scripts"
    # 检查脚本导入它们的兄弟``security_scan_common``； 在执行之前将脚本目录放在路径上，
    # 使其可导入。
    #
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_dep = _load_script_module("check_dependency_diff")

_is_trusted_registry = _dep._is_trusted_registry
_registry_host = _dep._registry_host
_source_label = _dep._source_label


# --- 可信来源 ------------------------------------------------------


def test_canonical_pypi_registry_is_trusted():
    assert _is_trusted_registry({"registry": "https://pypi.org/simple"}) is True


def test_files_pythonhosted_is_trusted():
    assert (
        _is_trusted_registry({"registry": "https://files.pythonhosted.org/x"}) is True
    )


def test_first_party_workspace_members_are_trusted():
    assert _is_trusted_registry({"editable": "."}) is True
    assert _is_trusted_registry({"virtual": "."}) is True


# --- 必须阻止的来源 ----------------------------------------------------------


def test_mirror_registry_blocks():
    # 备用索引/镜像不是规范主机 -> 不可信。
    assert _is_trusted_registry({"registry": "https://mirror.internal/simple"}) is False


def test_lookalike_host_is_not_trusted():
    # 经典的子字符串匹配绕过一定不能被忽略。
    assert (
        _is_trusted_registry({"registry": "https://pypi.org.evil.example/simple"})
        is False
    )


def test_git_source_blocks():
    assert _is_trusted_registry({"git": "https://github.com/foo/bar"}) is False


def test_url_source_blocks():
    assert _is_trusted_registry({"url": "https://example.com/pkg.whl"}) is False


def test_missing_or_empty_source_is_not_trusted():
    # 故意：未知/空的源形状失败关闭（块）而不是
    # 而不是作为默认的注册表包被挥手通过。
    assert _is_trusted_registry({}) is False
    assert _is_trusted_registry(None) is False
    assert _is_trusted_registry("weird") is False


# --- helper: 注册表主机提取------------------------------------


def test_registry_host_extracts_and_lowercases():
    assert _registry_host({"registry": "https://PyPI.org/simple"}) == "pypi.org"


def test_registry_host_none_for_non_registry():
    assert _registry_host({"git": "https://x"}) is None
    assert _registry_host({}) is None


# --- helper: 可读源标签 ----------------------------------------------------


def test_source_label_prefers_specific_keys():
    assert _source_label({"git": "https://github.com/foo/bar"}).startswith("git:")
    assert _source_label({"url": "https://x/pkg.whl"}).startswith("url:")
    assert _source_label({"registry": "https://pypi.org/simple"}).startswith(
        "registry:"
    )


def test_source_label_handles_non_dict():
    assert _source_label("plain") == "plain"
