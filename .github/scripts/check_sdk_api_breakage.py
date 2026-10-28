#!/usr/bin/env python3
"""使用 Griffe 检测已发布 OpenHands 包的 API 不兼容变更。

本脚本将当前工作区中的包与最新的 PyPI 发行版比较；如果当前版本已经发布，
则与对应发行版比较，以检测公开 API 的不兼容变更。

重点检查以下明确声明的公开接口：
- 通过 ``__all__`` 导出的符号
- 从通过 ``__all__`` 导出的类中移除的公共成员

本脚本执行两项政策：

1. **移除前必须经过弃用期**：被移除的导出项或公共类成员，必须已在
   *上一个*发行版中通过标准弃用工具标记为弃用，包括 ``@deprecated``
   装饰器，或 ``openhands.sdk.utils.deprecation`` 中的 ``warn_deprecated()``。
   基线弃用元数据必须表明当前版本已达到预定移除版本，且该目标至少晚于
   ``deprecated_in`` **5 个次版本发布**。对于类成员，建议使用带限定名的
   ``warn_deprecated`` 功能名称，例如 ``"LLM.some_method"``。

2. **提升 MINOR 版本**：任何移除或结构性的不兼容变更，都必须依照 SemVer
   至少提升一个 MINOR 版本。

本脚本与弃用机制互为补充：
- 弃用检查（``check_deprecations.py``）：执行清理期限要求
- 本脚本：防止未经预告的移除，并要求提升相应的 SemVer 版本
"""

from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from packaging import version as pkg_version
from packaging.requirements import Requirement


@dataclass(frozen=True)
class PackageConfig:
    """单个已发布包的配置。"""

    package: str  # 点分模块路径，例如 "openhands.sdk"
    distribution: str  # PyPI 发行包名称，例如 "openhands-sdk"
    source_dir: str  # 相对于仓库的目录，例如 "openhands-sdk"


@dataclass(frozen=True, slots=True)
class DeprecationMetadata:
    deprecated_in: str | None = None
    removed_in: str | None = None


@dataclass(frozen=True, slots=True)
class DeprecatedSymbols:
    """在源树中检测到的已弃用 SDK 个符号。

    ``top_level`` 与 ``LLM`` 一样跟踪模块级符号（导出）。
    ``qualified`` 跟踪类似 ``LLM.some_method`` 的类成员。
    ``metadata`` 存储每个特征的已解析的弃用时间表。
    """

    top_level: set[str] = frozenset()  # type: ignore[assignment]
    qualified: set[str] = frozenset()  # type: ignore[assignment]
    metadata: dict[str, DeprecationMetadata] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FieldDefaultChange:
    package: str
    object_path: str
    old_default: str
    new_default: str


DEPRECATION_RUNWAY_MINOR_RELEASES = 5
FIELD_DEFAULT_CHANGE_REPORT_ENV = "SDK_API_BREAKAGE_REPORT_PATH"


PACKAGES: tuple[PackageConfig, ...] = (
    PackageConfig(
        package="openhands.sdk",
        distribution="openhands-sdk",
        source_dir="openhands-sdk",
    ),
    PackageConfig(
        package="openhands.workspace",
        distribution="openhands-workspace",
        source_dir="openhands-workspace",
    ),
    PackageConfig(
        package="openhands.tools",
        distribution="openhands-tools",
        source_dir="openhands-tools",
    ),
)

ACP_DEPENDENCY = "agent-client-protocol"
ACP_SKIP_ENV = "ACP_VERSION_CHECK_SKIP"
ACP_SKIP_TOKEN = "skip-acp-check"
ACP_BASE_REF_ENV = "ACP_VERSION_CHECK_BASE_REF"


def _get_base_ref() -> str | None:
    base_ref = os.environ.get(ACP_BASE_REF_ENV) or os.environ.get("GITHUB_BASE_REF")
    if not base_ref:
        return None
    base_ref = base_ref.strip()
    return base_ref or None


def _has_package_source_changes(repo_root: str, base_ref: str) -> bool:
    """当包源自 base_ref 以来发生更改或比较失败时，返回 True。"""

    changed_files: list[str] | None = None
    for candidate in _git_ref_candidates(base_ref):
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{candidate}...HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            changed_files = result.stdout.splitlines()
            break

    if changed_files is None:
        print(
            f"::warning title=API breakage::Unable to diff against {base_ref}; "
            "running breakage checks"
        )
        return True

    package_prefixes = tuple(f"{cfg.source_dir}/" for cfg in PACKAGES)
    package_pyprojects = {f"{cfg.source_dir}/pyproject.toml" for cfg in PACKAGES}
    for changed_file in changed_files:
        if changed_file in package_pyprojects or changed_file.startswith(
            package_prefixes
        ):
            return True
    return False


def read_version_from_pyproject(path: str) -> str:
    """从 pyproject.toml 文件读取版本字符串。"""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    proj = data.get("project", {})
    v = proj.get("version")
    if not v:
        raise SystemExit(f"Could not read version from {path}")
    return str(v)


def _read_pyproject(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _bool_env(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _get_dependency_spec(project_data: dict, dependency: str) -> str | None:
    deps = project_data.get("project", {}).get("dependencies", [])
    for dep in deps:
        if dep.startswith(dependency):
            return dep
    return None


def _min_version_from_requirement(req_str: str) -> pkg_version.Version | None:
    try:
        req = Requirement(req_str)
    except Exception as exc:
        print(
            f"::warning title=ACP version::Unable to parse requirement "
            f"'{req_str}': {exc}"
        )
        return None

    lower_bounds: list[pkg_version.Version] = []
    for spec in req.specifier:
        if spec.operator in {">=", ">", "==", "~="}:
            try:
                lower_bounds.append(_parse_version(spec.version))
            except Exception as exc:
                print(
                    f"::warning title=ACP version::Unable to parse version "
                    f"'{spec.version}' from '{req_str}': {exc}"
                )

    if not lower_bounds:
        return None

    return max(lower_bounds)


def _git_ref_candidates(ref: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys((f"origin/{ref}", ref)))


def _git_show_file(ref: str, rel_path: str) -> str | None:
    for candidate in _git_ref_candidates(ref):
        result = subprocess.run(
            ["git", "show", f"{candidate}:{rel_path}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
    return None


def _git_archive_directory(
    repo_root: str,
    ref: str,
    rel_path: str,
    dest_root: str,
) -> bool:
    for candidate in _git_ref_candidates(ref):
        result = subprocess.run(
            ["git", "archive", "--format=tar", candidate, rel_path],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            continue

        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
            archive.extractall(dest_root, filter="data")
        return True

    return False


def _load_base_pyproject(base_ref: str) -> dict | None:
    rel_path = "openhands-sdk/pyproject.toml"
    content = _git_show_file(base_ref, rel_path)
    if content is None:
        print(
            f"::warning title=ACP version::Unable to read {rel_path} from "
            f"{base_ref}; skipping ACP version check"
        )
        return None
    try:
        return tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"::warning title=ACP version::Failed to parse {rel_path} from "
            f"{base_ref}: {exc}"
        )
        return None


def _check_acp_version_bump(repo_root: str) -> int:
    if _bool_env(ACP_SKIP_ENV):
        print(
            f"::notice title=ACP version::Skipping ACP version check because "
            f"{ACP_SKIP_ENV} is set (token: [{ACP_SKIP_TOKEN}])."
        )
        return 0

    base_ref = _get_base_ref()
    if not base_ref:
        print(
            "::warning title=ACP version::No base ref found; skipping ACP version check"
        )
        return 0

    base_data = _load_base_pyproject(base_ref)
    if base_data is None:
        return 0

    current_data = _read_pyproject(
        os.path.join(repo_root, "openhands-sdk", "pyproject.toml")
    )
    old_req = _get_dependency_spec(base_data, ACP_DEPENDENCY)
    new_req = _get_dependency_spec(current_data, ACP_DEPENDENCY)

    if not old_req or not new_req:
        print(
            f"::warning title=ACP version::Unable to locate {ACP_DEPENDENCY} "
            "dependency in pyproject.toml; skipping ACP version check"
        )
        return 0

    old_min = _min_version_from_requirement(old_req)
    new_min = _min_version_from_requirement(new_req)

    if old_min is None or new_min is None:
        print(
            f"::warning title=ACP version::Unable to parse {ACP_DEPENDENCY} "
            "minimum version; skipping ACP version check"
        )
        return 0

    if new_min <= old_min:
        return 0

    if new_min.major != old_min.major or new_min.minor != old_min.minor:
        print(
            "::error title=ACP version::Detected "
            f"{ACP_DEPENDENCY} minor/major version bump "
            f"({old_req} -> {new_req}). If intentional, add "
            f"[{ACP_SKIP_TOKEN}] to the PR description to bypass."
        )
        return 1

    return 0


def _parse_version(v: str) -> pkg_version.Version:
    """使用打包解析版本字符串。"""
    return pkg_version.parse(v)


def _parse_string_kwarg(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg != name:
            continue
        value = kw.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        return None
    return None


def _minimum_removed_in(deprecated_in: str) -> str:
    parsed = _parse_version(deprecated_in)
    return f"{parsed.major}.{parsed.minor + DEPRECATION_RUNWAY_MINOR_RELEASES}.0"


def _deprecation_schedule_errors(
    *,
    feature: str,
    metadata: DeprecationMetadata | None,
    current_version: str,
) -> list[str]:
    if metadata is None:
        return [
            f"Removed '{feature}' without prior deprecation. Mark it with "
            "@deprecated(...) or warn_deprecated(...), and keep it deprecated for "
            f"{DEPRECATION_RUNWAY_MINOR_RELEASES} minor releases before removing."
        ]

    if metadata.deprecated_in is None:
        return [
            f"Removed '{feature}' was marked deprecated previously, but its "
            "deprecation metadata does not declare deprecated_in. Public API "
            f"removals require {DEPRECATION_RUNWAY_MINOR_RELEASES} minor releases "
            "of runway."
        ]

    if metadata.removed_in is None:
        return [
            f"Removed '{feature}' was marked deprecated previously, but its "
            "deprecation metadata does not declare removed_in. Public API removals "
            f"require {DEPRECATION_RUNWAY_MINOR_RELEASES} minor releases of runway."
        ]

    minimum_removed_in = _minimum_removed_in(metadata.deprecated_in)
    if _parse_version(metadata.removed_in) < _parse_version(minimum_removed_in):
        return [
            f"Removed '{feature}' uses an invalid deprecation schedule: "
            f"deprecated_in={metadata.deprecated_in} and "
            f"removed_in={metadata.removed_in}. Public API removals require at "
            f"least {DEPRECATION_RUNWAY_MINOR_RELEASES} minor releases of runway "
            f"(minimum removed_in: {minimum_removed_in})."
        ]

    if _parse_version(current_version) < _parse_version(metadata.removed_in):
        return [
            f"Removed '{feature}' before its scheduled removal version "
            f"{metadata.removed_in}. Current version is {current_version}. Public "
            f"API removals require {DEPRECATION_RUNWAY_MINOR_RELEASES} minor releases "
            "of deprecation runway."
        ]

    return []


def get_pypi_baseline_version(pkg: str, current: str | None) -> str | None:
    """从 PyPI 获取基线发行版本。

    基准是与当前工作区对比的最近发布的版本。 如果当前版本已存在于 PyPI 上，请与同一版
    本进行比较。 否则，请回退到比当前版本旧的最新版本。 如果
    ``current`` 为 None，则使用最新版本。

    Args:
        pkg: PyPI 上的包名称（e.g.、“OpenHands-SDK”）
        current: 当前版本来自工作区，或 None 为最新版本

    Returns:
        基线版本字符串，如果未找到或出现网络错误，则为 None
    """
    req = urllib.request.Request(
        url=f"https://pypi.org/pypi/{pkg}/json",
        headers={"User-Agent": "openhands-sdk-api-check/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            meta = json.load(r)
    except Exception as e:
        print(f"::warning title={pkg} API::Failed to fetch PyPI metadata: {e}")
        return None

    releases = list(meta.get("releases", {}).keys())
    if not releases:
        return None

    def _sort_key(s: str):
        return _parse_version(s)

    releases_sorted = sorted(releases, key=_sort_key, reverse=True)
    if current is None:
        return releases_sorted[0]

    if current in releases:
        return current

    cur_parsed = _parse_version(current)
    older = [rv for rv in releases if _parse_version(rv) < cur_parsed]
    if not older:
        return None
    return sorted(older, key=_sort_key, reverse=True)[0]


def ensure_griffe() -> None:
    """验证 griffe 是否已安装，如果未安装，则会引发错误。"""
    try:
        import griffe  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "ERROR: griffe not installed. Install with: pip install griffe[pypi]\n"
        )
        raise SystemExit(1)


FIELD_METADATA_KWARGS = frozenset(
    {
        "deprecated",
        "description",
        "examples",
        "json_schema_extra",
        "title",
    }
)


def _escape_newlines_in_string_literals(text: str) -> str:
    """转义出现在带引号的字符串文字内的文字换行符。"""
    chars: list[str] = []
    in_string: str | None = None
    escaped = False

    for ch in text:
        if in_string is None:
            chars.append(ch)
            if ch in {"'", '"'}:
                in_string = ch
            continue

        if escaped:
            chars.append(ch)
            escaped = False
            continue

        if ch == "\\":
            chars.append(ch)
            escaped = True
            continue

        if ch == in_string:
            chars.append(ch)
            in_string = None
            continue

        if ch == "\n":
            chars.append("\\n")
            continue

        chars.append(ch)

    return "".join(chars)


def _parse_field_call(value: object) -> ast.Call | None:
    """将字符串化的 Pydantic ``Field(...)`` 值解析为 AST 调用。"""
    try:
        expr = ast.parse(
            _escape_newlines_in_string_literals(str(value)),
            mode="eval",
        ).body
    except SyntaxError:
        return None

    if not isinstance(expr, ast.Call):
        return None

    func = expr.func
    if isinstance(func, ast.Name):
        func_name = func.id
    elif isinstance(func, ast.Attribute):
        func_name = func.attr
    else:
        return None

    if func_name != "Field":
        return None

    return expr


def _filter_field_metadata_kwargs(call: ast.Call) -> ast.Call:
    """返回不带仅元数据 kwargs 的 ``Field(...)`` 调用的副本。"""
    return ast.Call(
        func=call.func,
        args=call.args,
        keywords=[kw for kw in call.keywords if kw.arg not in FIELD_METADATA_KWARGS],
    )


FIELD_DEFAULT_KWARGS = ("default", "default_factory")


def _field_default_node(call: ast.Call) -> ast.AST | None:
    """返回表示 ``Field`` 默认值/工厂的 AST 节点。"""
    for kw in call.keywords:
        if kw.arg in FIELD_DEFAULT_KWARGS:
            return kw.value
    if call.args:
        return call.args[0]
    return None


def _remove_field_default(call: ast.Call) -> ast.Call:
    """返回 ``Field(...)`` 调用的副本，不带默认值/工厂。"""
    args = list(call.args)
    if args:
        args = args[1:]
    return ast.Call(
        func=call.func,
        args=args,
        keywords=[kw for kw in call.keywords if kw.arg not in FIELD_DEFAULT_KWARGS],
    )


def _field_default_repr(value: object) -> str | None:
    """返回 ``Field`` 默认值/工厂（如果存在）的字符串形式。"""
    call = _parse_field_call(value)
    if call is None:
        return None
    default_node = _field_default_node(call)
    if default_node is None:
        return None
    return ast.unparse(default_node)


def _is_field_default_only_change(old_val: object, new_val: object) -> bool:
    """检查是否仅更改了``Field``默认值。

    仅元数据 kwargs 会被忽略，但任何其他语义 ``Field`` 参数更改仍然算作真正的 API 损
    坏。
    """
    old_call = _parse_field_call(old_val)
    new_call = _parse_field_call(new_val)
    if old_call is None or new_call is None:
        return False

    old_default = _field_default_node(old_call)
    new_default = _field_default_node(new_call)
    if old_default is None or new_default is None:
        return False

    if ast.dump(old_default, include_attributes=False) == ast.dump(
        new_default,
        include_attributes=False,
    ):
        return False

    return ast.dump(
        _remove_field_default(_filter_field_metadata_kwargs(old_call)),
        include_attributes=False,
    ) == ast.dump(
        _remove_field_default(_filter_field_metadata_kwargs(new_call)),
        include_attributes=False,
    )


def _is_field_metadata_only_change(old_val: object, new_val: object) -> bool:
    """检查更改是否仅发生在字段元数据（描述、标题等）中。

    字段元数据参数，例如 ``description``、``title``、``examples``、
    ``json_schema_extra`` 和 ``deprecated`` 不影响运行时行为。 对这些的更改不应被视为
    破坏性 API 更改。

    Returns:
        True 如果两个值都是 Field() 调用并且只有元数据参数不同。
    """
    old_call = _parse_field_call(old_val)
    new_call = _parse_field_call(new_val)
    if old_call is None or new_call is None:
        return False

    return ast.dump(
        _filter_field_metadata_kwargs(old_call),
        include_attributes=False,
    ) == ast.dump(
        _filter_field_metadata_kwargs(new_call),
        include_attributes=False,
    )


def _object_path(obj: object | None) -> str:
    """返回可用于 griffe 对象的最具体的路径。"""
    if obj is None:
        return "<unknown>"
    return str(
        getattr(obj, "path", None)
        or getattr(obj, "canonical_path", None)
        or getattr(obj, "name", None)
        or "<unknown>"
    )


def _write_field_default_change_report(
    changes: list[FieldDefaultChange],
    *,
    field_default_changes_since_base: list[FieldDefaultChange] | None = None,
) -> None:
    """将检测到的公共字段默认更改写入 JSON 报告文件。"""
    report_path = os.environ.get(FIELD_DEFAULT_CHANGE_REPORT_ENV, "").strip()
    if not report_path:
        return

    report = {"field_default_changes": [asdict(change) for change in changes]}
    if field_default_changes_since_base is not None:
        report["field_default_changes_since_base"] = [
            asdict(change) for change in field_default_changes_since_base
        ]

    Path(report_path).write_text(json.dumps(report, indent=2) + "\n")


def _member_deprecation_metadata(
    cls_obj: object,
    member_name: str,
    deprecated: DeprecatedSymbols,
) -> DeprecationMetadata | None:
    """返回类成员的弃用元数据，包括父类。

    当像 ``system_message`` 这样的成员在基类 (``AgentBase``) 上是已弃用但从子类 (
    ``Agent``) 中删除时，griffe 会
    根据子类名称报告删除情况。 这个助手遍历 MRO 以便
    ``Agent.system_message`` 重用了基类弃用的 schedule。
    """
    cls_name = getattr(cls_obj, "name", "")
    feature = f"{cls_name}.{member_name}"
    if feature in deprecated.qualified:
        return deprecated.metadata.get(feature, DeprecationMetadata())
    if cls_name in deprecated.top_level:
        return deprecated.metadata.get(cls_name, DeprecationMetadata())

    for base in getattr(cls_obj, "resolved_bases", []):
        base_name = getattr(base, "name", None)
        if base_name is None:
            continue
        feature = f"{base_name}.{member_name}"
        if feature in deprecated.qualified:
            return deprecated.metadata.get(feature, DeprecationMetadata())
    return None


def _was_deprecated(
    cls_obj: object,
    member_name: str,
    deprecated: DeprecatedSymbols,
) -> bool:
    return _member_deprecation_metadata(cls_obj, member_name, deprecated) is not None


def _collect_breakages_pairs(
    objs: Iterable[tuple[object, object]],
    *,
    deprecated: DeprecatedSymbols,
    current_version: str,
    title: str,
    package: str,
    field_default_changes: list[FieldDefaultChange] | None = None,
    field_defaults_only: bool = False,
    emit_diagnostics: bool = True,
) -> tuple[list[object], int]:
    """在旧/新 API 对象对之间查找不兼容变更。

    仅报告公共 API 成员的损坏情况。

    Returns:
        （破损，removal_policy_errors）
    """

    import griffe
    from griffe import Alias, AliasResolutionError, BreakageKind, ExplanationStyle, Kind

    breakages: list[object] = []
    removal_policy_errors = 0

    for old, new in objs:
        try:
            for br in griffe.find_breaking_changes(old, new):
                obj = getattr(br, "obj", None)
                if not getattr(obj, "is_public", True):
                    continue

                if br.kind == BreakageKind.ATTRIBUTE_CHANGED_VALUE:
                    old_value = getattr(br, "old_value", None)
                    new_value = getattr(br, "new_value", None)
                    if _is_field_metadata_only_change(old_value, new_value):
                        if emit_diagnostics:
                            print(
                                f"::notice title={title}::Ignoring Field "
                                "metadata-only change (non-breaking): "
                                f"{obj.name if obj else 'unknown'}"
                            )
                        continue
                    if _is_field_default_only_change(old_value, new_value):
                        object_path = _object_path(obj)
                        old_default = _field_default_repr(old_value) or "<unknown>"
                        new_default = _field_default_repr(new_value) or "<unknown>"
                        if emit_diagnostics:
                            print(
                                f"::warning title={title}::Public Field default "
                                "changed (release-note-required): "
                                f"{object_path} {old_default} -> {new_default}"
                            )
                        if field_default_changes is not None:
                            field_default_changes.append(
                                FieldDefaultChange(
                                    package=package,
                                    object_path=object_path,
                                    old_default=old_default,
                                    new_default=new_default,
                                )
                            )
                        continue

                if field_defaults_only:
                    continue

                print(br.explain(style=ExplanationStyle.GITHUB))
                breakages.append(br)

                if br.kind != BreakageKind.OBJECT_REMOVED:
                    continue

                parent = getattr(obj, "parent", None)
                if getattr(parent, "kind", None) != Kind.CLASS:
                    continue

                feature = f"{parent.name}.{obj.name}"
                errors = _deprecation_schedule_errors(
                    feature=feature,
                    metadata=_member_deprecation_metadata(parent, obj.name, deprecated),
                    current_version=current_version,
                )
                if not errors:
                    continue

                for error in errors:
                    print(f"::error title={title}::{error}")
                removal_policy_errors += len(errors)
        except AliasResolutionError as e:
            if field_defaults_only:
                continue
            if isinstance(old, Alias) or isinstance(new, Alias):
                old_target = old.target_path if isinstance(old, Alias) else None
                new_target = new.target_path if isinstance(new, Alias) else None
                if old_target != new_target:
                    name = getattr(old, "name", None) or getattr(
                        new, "name", "<unknown>"
                    )
                    print(
                        f"::warning title={title}::Alias target changed for '{name}': "
                        f"{old_target!r} -> {new_target!r}"
                    )
                    breakages.append(
                        {
                            "kind": "ALIAS_TARGET_CHANGED",
                            "name": name,
                            "old": old_target,
                            "new": new_target,
                        }
                    )
            else:
                print(
                    f"::notice title={title}::Skipping symbol comparison due to "
                    f"unresolved alias: {e}"
                )
        except Exception as e:
            if field_defaults_only:
                raise RuntimeError("Failed to collect Field default changes") from e
            print(f"::warning title={title}::Failed to compute breakages: {e}")

    return breakages, removal_policy_errors


def _extract_exported_names(module) -> set[str]:
    """通过 ``__all__`` 提取从模块导出的名称。

    此检查的明确目的是跟踪策划的公共表面。 SDK预计在``openhands.sdk``中定义
    ``__all__``； 如果缺失或无法静态解析，我们快速失败而不是无声
    扩大表面（这会使检查变得噪音和脆弱）。
    """
    try:
        all_var = module["__all__"]
    except Exception as e:
        raise ValueError("Expected __all__ to be defined on the public module") from e

    val = getattr(all_var, "value", None)
    elts = getattr(val, "elements", None)
    if not elts:
        raise ValueError("Unable to statically evaluate __all__")

    names: set[str] = set()
    for el in elts:
        # Griffe 以不同的方式表示 __all__ 中的字符串文字，具体取决于模块的加载方式/
        # griffe 版本：
        # - 有时作为纯 Python 字符串（包括引号、e.g. "'LLM'")
        # - 有时作为具有 `.value` 属性的表达式节点
        #
        # 我们有意只支持“字符串文字的 static __all__”情况； 我们只是标准化表示。
        #
        if isinstance(el, str):
            names.add(el.strip("\"'"))
            continue
        s = getattr(el, "value", None)
        if isinstance(s, str):
            names.add(s)

    if not names:
        raise ValueError("__all__ resolved to an empty set")

    return names


def _check_version_bump(prev: str, new_version: str, total_breaks: int) -> int:
    """检查不兼容变更是否满足版本更新政策。

    Policy: 不兼容变更至少需要 MINOR 版本升级。

    Returns:
        如果满足策略则为 0，如果不满足则为 1
    """
    if total_breaks == 0:
        print("No breaking changes detected")
        return 0

    parsed_prev = _parse_version(prev)
    parsed_new = _parse_version(new_version)

    # MINOR 需要提升：相同专业、更高的辅修课程或更高的专业课程
    ok = (parsed_new.major > parsed_prev.major) or (
        parsed_new.major == parsed_prev.major and parsed_new.minor > parsed_prev.minor
    )

    if not ok:
        print(
            f"::error title=SemVer::Breaking changes detected ({total_breaks}); "
            f"require at least minor version bump from "
            f"{parsed_prev.major}.{parsed_prev.minor}.x, but new is {new_version}"
        )
        return 1

    print(
        f"Breaking changes detected ({total_breaks}) and version bump policy "
        f"satisfied ({prev} -> {new_version})"
    )
    return 0


def _resolve_griffe_object(
    root: object,
    dotted: str,
    root_package: str = "",
) -> object:
    """解析指向 Griffe 对象的虚线路径。"""
    root_path = getattr(root, "path", None)
    if root_path == dotted:
        return root

    if isinstance(root_path, str) and dotted.startswith(root_path + "."):
        dotted = dotted[len(root_path) + 1 :]

    try:
        return root[dotted]
    except (KeyError, TypeError) as e:
        print(
            f"::warning title=SDK API::Unable to resolve {dotted} via "
            f"direct lookup; falling back to manual traversal: {e}"
        )

    rel = dotted
    if root_package and dotted.startswith(root_package + "."):
        rel = dotted[len(root_package) + 1 :]

    obj = root
    for part in rel.split("."):
        try:
            obj = obj[part]
        except (KeyError, TypeError) as e:
            raise KeyError(f"Unable to resolve {dotted}: failed at {part}") from e
    return obj


def _load_current(
    griffe_module: object, repo_root: str, cfg: PackageConfig
) -> object | None:
    try:
        return griffe_module.load(
            cfg.package,
            search_paths=[os.path.join(repo_root, cfg.source_dir)],
        )
    except Exception as e:
        print(
            f"::error title={cfg.distribution} API::"
            f"Failed to load current {cfg.distribution}: {e}"
        )
        return None


@contextmanager
def _load_from_git_ref(
    griffe_module: object,
    repo_root: str,
    ref: str,
    cfg: PackageConfig,
):
    title = f"{cfg.distribution} API"
    with tempfile.TemporaryDirectory() as tmpdir:
        if not _git_archive_directory(repo_root, ref, cfg.source_dir, tmpdir):
            print(
                f"::warning title={title}::Failed to load {cfg.distribution} from "
                f"git ref {ref}: unable to archive {cfg.source_dir}"
            )
            yield None
            return

        try:
            yield griffe_module.load(
                cfg.package,
                search_paths=[os.path.join(tmpdir, cfg.source_dir)],
            )
        except Exception as e:
            print(
                f"::warning title={title}::Failed to load {cfg.distribution} from "
                f"git ref {ref}: {e}"
            )
            yield None


def _load_prev_from_pypi(
    griffe_module: object,
    prev: str,
    cfg: PackageConfig,
) -> object | None:
    griffe_cache = os.path.expanduser("~/.cache/griffe")
    os.makedirs(griffe_cache, exist_ok=True)

    try:
        return griffe_module.load_pypi(
            package=cfg.package,
            distribution=cfg.distribution,
            version_spec=f"=={prev}",
        )
    except Exception as e:
        print(
            f"::error title={cfg.distribution} API::"
            f"Failed to load {cfg.distribution}=={prev} from PyPI: {e}"
        )
        return None


def _collect_field_default_changes_since_ref(
    griffe_module: object,
    repo_root: str,
    ref: str,
    cfg: PackageConfig,
) -> list[FieldDefaultChange] | None:
    new_root = _load_current(griffe_module, repo_root, cfg)
    if not new_root:
        return None

    with _load_from_git_ref(griffe_module, repo_root, ref, cfg) as old_root:
        if not old_root:
            return None

        changes: list[FieldDefaultChange] = []
        try:
            _compute_breakages(
                old_root,
                new_root,
                cfg,
                field_default_changes=changes,
                field_defaults_only=True,
                emit_diagnostics=False,
            )
        except Exception as e:
            print(
                f"::warning title={cfg.distribution} API::Failed to compare "
                f"Field defaults against base ref {ref}: {e}"
            )
            return None

    return changes


# 模块级数据注册表的名称，将已弃用公共重新导出声明为
# ``{name: {"deprecated_in": ..., "removed_in": ...}}`` 并由模块级 ``__getattr__`` 使用
# 。 SDK采用这种形式进行重命名
#
# export aliases (e.g. ``LLMAgentSettings``) that deliberately are NOT
# ``@deprecated`` - 装饰在类本身上（该类仍然是实时内部联合成员），其 ``warn_deprecated``
#  功能名称是动态 f 字符串。 这样的弃用项对于下面的装饰器/调用扫描是不可见的，因此我们将
# 注册表视为第三个弃用源。
#
_DEPRECATED_EXPORT_REGISTRY_NAMES = frozenset({"_DEPRECATED_SDK_EXPORTS"})


def _find_deprecated_symbols(source_root: Path) -> DeprecatedSymbols:
    """扫描源文件中标有 SDK 弃用帮助程序的符号。

    检测三种形式：
    - ``@deprecated(...)`` 类/函数/方法上的装饰器
    - ``warn_deprecated('SomeFeature', ...)`` 致电
    - ``_DEPRECATED_SDK_EXPORTS`` 样式注册表字典中的条目映射
      export name to ``{"deprecated_in": ..., "removed_in": ...}``

    Returns:
        DeprecatedSymbols(top_level=..., qualified=..., metadata=...)
    """

    def _deprecated_metadata(call: ast.Call) -> DeprecationMetadata:
        return DeprecationMetadata(
            deprecated_in=_parse_string_kwarg(call, "deprecated_in"),
            removed_in=_parse_string_kwarg(call, "removed_in"),
        )

    def _is_deprecated_decorator(deco: ast.AST) -> ast.Call | None:
        if not isinstance(deco, ast.Call):
            return None
        target = deco.func
        if isinstance(target, ast.Name) and target.id == "deprecated":
            return deco
        if isinstance(target, ast.Attribute) and target.attr == "deprecated":
            return deco
        return None

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str] = []
            self.top_level: set[str] = set()
            self.qualified: set[str] = set()
            self.metadata: dict[str, DeprecationMetadata] = {}

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            for deco in node.decorator_list:
                deprecated_call = _is_deprecated_decorator(deco)
                if deprecated_call is None:
                    continue
                metadata = _deprecated_metadata(deprecated_call)
                self.top_level.add(node.name)
                self.qualified.add(node.name)
                self.metadata[node.name] = metadata
                break

            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def _visit_function_like(
            self,
            node: ast.FunctionDef | ast.AsyncFunctionDef,
        ) -> None:
            for deco in node.decorator_list:
                deprecated_call = _is_deprecated_decorator(deco)
                if deprecated_call is None:
                    continue
                metadata = _deprecated_metadata(deprecated_call)
                if self.class_stack:
                    feature = ".".join([*self.class_stack, node.name])
                    self.qualified.add(feature)
                    self.metadata[feature] = metadata
                else:
                    self.top_level.add(node.name)
                    self.qualified.add(node.name)
                    self.metadata[node.name] = metadata
                break

            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._visit_function_like(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._visit_function_like(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            target = node.func
            func_name = None
            if isinstance(target, ast.Name):
                func_name = target.id
            elif isinstance(target, ast.Attribute):
                func_name = target.attr

            if func_name == "warn_deprecated" and node.args:
                feature = _extract_string_literal(node.args[0])
                if feature is not None:
                    metadata = _deprecated_metadata(node)
                    self.qualified.add(feature)
                    top_level_name = feature.split(".")[0]
                    self.top_level.add(top_level_name)
                    self.metadata[feature] = metadata
                    self.metadata.setdefault(top_level_name, metadata)

            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
            self._record_export_registry(node.target, node.value)
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            for target in node.targets:
                self._record_export_registry(target, node.value)
            self.generic_visit(node)

        def _record_export_registry(
            self, target: ast.expr, value: ast.expr | None
        ) -> None:
            """通过注册表字典文字声明已弃用的记录导出。"""
            if not (
                isinstance(target, ast.Name)
                and target.id in _DEPRECATED_EXPORT_REGISTRY_NAMES
            ):
                return
            if not isinstance(value, ast.Dict):
                return
            for key_node, val_node in zip(value.keys, value.values):
                if key_node is None:
                    continue
                export = _extract_string_literal(key_node)
                if export is None or not isinstance(val_node, ast.Dict):
                    continue
                metadata = DeprecationMetadata(
                    deprecated_in=_extract_dict_string_value(val_node, "deprecated_in"),
                    removed_in=_extract_dict_string_value(val_node, "removed_in"),
                )
                self.top_level.add(export)
                self.qualified.add(export)
                self.metadata[export] = metadata

    top_level: set[str] = set()
    qualified: set[str] = set()
    metadata: dict[str, DeprecationMetadata] = {}

    for pyfile in source_root.rglob("*.py"):
        try:
            tree = ast.parse(pyfile.read_text())
        except SyntaxError as e:
            print(
                f"::warning title=SDK API::Skipping {pyfile}: "
                f"failed to parse (SyntaxError: {e})"
            )
            continue

        visitor = _Visitor()
        visitor.visit(tree)
        top_level |= visitor.top_level
        qualified |= visitor.qualified
        metadata.update(visitor.metadata)

    return DeprecatedSymbols(
        top_level=top_level, qualified=qualified, metadata=metadata
    )


def _extract_string_literal(node: ast.AST) -> str | None:
    """如果 *node* 是简单字符串文字，则返回字符串值。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_dict_string_value(node: ast.Dict, key: str) -> str | None:
    """返回 ``ast.Dict`` 文字中 *key* 的字符串值（如果存在）。"""
    for k, v in zip(node.keys, node.values):
        if (
            isinstance(k, ast.Constant)
            and k.value == key
            and isinstance(v, ast.Constant)
            and isinstance(v.value, str)
        ):
            return v.value
    return None


def _get_source_root(griffe_root: object) -> Path | None:
    """从 griffe 模块的文件路径派生包源目录。"""
    filepath = getattr(griffe_root, "filepath", None)
    if filepath is not None:
        return Path(filepath).parent
    return None


def _compute_breakages(
    old_root,
    new_root,
    cfg: PackageConfig,
    *,
    current_version: str = "9999.0.0",
    field_default_changes: list[FieldDefaultChange] | None = None,
    field_defaults_only: bool = False,
    emit_diagnostics: bool = True,
) -> tuple[int, int]:
    """检测新旧软件包版本之间的不兼容变更。

    Returns:
        ``(total_breaks, removal_policy_errors)`` — *total_breaks* 计算所有结构破坏（
        对于版本冲突策略），
        而
        *removal_policy_errors* 统计违反规定的公开 API 删除
        需要弃用跑道。
    """
    pkg = cfg.package
    title = f"{cfg.distribution} API"
    total_breaks = 0
    removal_policy_errors = 0

    source_root = _get_source_root(old_root)
    deprecated = (
        _find_deprecated_symbols(source_root) if source_root else DeprecatedSymbols()
    )

    try:
        old_mod = _resolve_griffe_object(old_root, pkg, root_package=pkg)
        new_mod = _resolve_griffe_object(new_root, pkg, root_package=pkg)
    except Exception as e:
        raise RuntimeError(f"Failed to resolve root module '{pkg}'") from e

    new_exports = _extract_exported_names(new_mod)
    try:
        old_exports = _extract_exported_names(old_mod)
    except ValueError as e:
        # API 破损检查依赖于通过 __all__ 定义的策划公共表面。 如果基线版本没有定义（或无
        # 法静态评估）__全部__，我们就无法计算有意义的损坏。
        #
        # 在这种情况下，跳过整个工作流程而不是失败。
        if emit_diagnostics:
            print(
                f"::notice title={title}::Skipping breakage check; baseline release "
                f"has no statically-evaluable {pkg}.__all__: {e}"
            )
        return 0, 0

    if not field_defaults_only:
        removed = sorted(old_exports - new_exports)

        # 检查弃用跑道政策（出口）
        for name in removed:
            total_breaks += 1  # 每一次拆除都是一次结构性破坏
            errors = _deprecation_schedule_errors(
                feature=name,
                metadata=(
                    deprecated.metadata.get(name, DeprecationMetadata())
                    if name in deprecated.top_level
                    else None
                ),
                current_version=current_version,
            )
            if not errors:
                print(
                    f"::notice title={title}::Removed previously-deprecated symbol "
                    f"'{name}' from {pkg}.__all__ after its scheduled removal version"
                )
                continue

            for error in errors:
                print(f"::error title={title}::{error}")
            removal_policy_errors += len(errors)

    common = sorted(old_exports & new_exports)
    pairs: list[tuple[object, object]] = []
    for name in common:
        try:
            pairs.append((old_mod[name], new_mod[name]))
        except Exception as e:
            if emit_diagnostics:
                print(f"::warning title={title}::Unable to resolve symbol {name}: {e}")

    breakages, member_policy_errors = _collect_breakages_pairs(
        pairs,
        deprecated=deprecated,
        current_version=current_version,
        title=title,
        package=cfg.package,
        field_default_changes=field_default_changes,
        field_defaults_only=field_defaults_only,
        emit_diagnostics=emit_diagnostics,
    )
    total_breaks += len(breakages)
    removal_policy_errors += member_policy_errors

    return total_breaks, removal_policy_errors


def _check_package(
    griffe_module,
    repo_root: str,
    cfg: PackageConfig,
    *,
    field_default_changes: list[FieldDefaultChange] | None = None,
) -> int:
    """对单个包裹运行破损检查。 成功则返回 0。"""
    pyproj = os.path.join(repo_root, cfg.source_dir, "pyproject.toml")
    new_version = read_version_from_pyproject(pyproj)

    title = f"{cfg.distribution} API"
    baseline = get_pypi_baseline_version(cfg.distribution, new_version)
    if not baseline:
        print(
            f"::warning title={title}::No baseline {cfg.distribution} "
            f"release found; skipping breakage check",
        )
        return 0

    print(f"Comparing {cfg.distribution} {new_version} against {baseline}")

    new_root = _load_current(griffe_module, repo_root, cfg)
    if not new_root:
        return 1

    old_root = _load_prev_from_pypi(griffe_module, baseline, cfg)
    if not old_root:
        return 1

    try:
        total_breaks, removal_policy_errors = _compute_breakages(
            old_root,
            new_root,
            cfg,
            current_version=new_version,
            field_default_changes=field_default_changes,
        )
    except Exception as e:
        print(f"::error title={title}::Failed to compute breakages: {e}")
        return 1

    if removal_policy_errors:
        print(
            f"::error title={title}::{removal_policy_errors} public API removal "
            f"policy violation(s) detected in {cfg.package} — see errors above"
        )

    bump_rc = _check_version_bump(baseline, new_version, total_breaks)

    return 1 if (removal_policy_errors or bump_rc) else 0


def main() -> int:
    """主要入口用于API破损检测。"""
    repo_root = os.getcwd()
    rc = _check_acp_version_bump(repo_root)
    base_ref = _get_base_ref()
    if base_ref and not _has_package_source_changes(repo_root, base_ref):
        print(
            "::notice title=API breakage::No package source changes since "
            f"{base_ref}; skipping SDK API breakage checks"
        )
        _write_field_default_change_report([], field_default_changes_since_base=[])
        return rc

    ensure_griffe()
    import griffe

    field_default_changes: list[FieldDefaultChange] = []
    field_default_changes_since_base: list[FieldDefaultChange] | None = []
    for cfg in PACKAGES:
        print(f"\n{'=' * 60}")
        print(f"Checking {cfg.distribution} ({cfg.package})")
        print(f"{'=' * 60}")
        rc |= _check_package(
            griffe,
            repo_root,
            cfg,
            field_default_changes=field_default_changes,
        )
        if base_ref and field_default_changes_since_base is not None:
            changes_since_base = _collect_field_default_changes_since_ref(
                griffe,
                repo_root,
                base_ref,
                cfg,
            )
            if changes_since_base is None:
                field_default_changes_since_base = None
            else:
                field_default_changes_since_base.extend(changes_since_base)

    _write_field_default_change_report(
        field_default_changes,
        field_default_changes_since_base=(
            field_default_changes_since_base if base_ref else None
        ),
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
