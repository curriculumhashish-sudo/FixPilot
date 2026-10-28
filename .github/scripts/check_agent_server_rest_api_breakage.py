#!/usr/bin/env python3
"""REST API 使用 oasdiff 对 OpenHands-智能体-服务器进行损坏检测。

这个脚本比较了当前 OpenAPI  模式对于公众智能体-server REST  API (the) `/api/**` 在已
发布的版本上对抗。 基准版本是从选择的
PyPI, 但基准模式从当前的匹配的 git 标签生成的工作区锁定的依赖集。 这保持了比较的焦点
在 API 在我们的代码中，不是模式从更新处偏离
FastAPIPydantic 发行版本。

它识别的弃用注释有意与 Python 弃用检查所使用的措辞相匹配，例如：

    Deprecated since v1.14.0 and scheduled for removal in v1.19.0.

执行政策：

1) REST 弃用项必须使用 FastAPI/OpenAPI 元数据
   - FastAPI 路由处理程序不得使用 `openhands.sdk.utils.deprecation.deprecated`。
   - 端点在其 OpenAPI 描述中记录为已弃用，也必须在生成的模式中标记为
   `deprecated: true`。

2) 弃用拆除前的跑道
   - 如果移除了 REST 操作（路径 + HTTP 方法）或模式属性，必须在基线版本中标记
   `deprecated: true`，并且其 OpenAPI 描述必须声明
   一个已达到的计划移除版本，该版本由当前包版本达到。

3) 允许附加请求/响应 oneOf/anyOf 扩展
   - 在请求或响应模式中添加``oneOf``或``anyOf``的扩展型APIs成员是正常的发展。 客户端
   必须优雅地处理未知的标识符值（跳过/忽略）。
   - oasdiff 可以将联合扩展报告为 ERR 加上仍存在于一个联合成员上的字段的辅助类型更改
   或属性删除工件； 该脚本将这些工件降级为信息通知。

4) 发布说明允许加性响应属性类型加宽
   - 如果响应属性的旧类型仍然有效，且只有模式添加了新的接受类型，则检查通过，并且工作
   流标记为 PR 需要发布注释。

5) 模式-仅允许修复以前不透明的 MCP/设置位置
   - 运行时已在这些位置返回 MCP 个对象，但历史 OpenAPI 将它们描述为空/不受约束模式。
   赋予这些现有对象真实的形状并不是线格式的改变。
   - Pydantic 也可能会折叠相同的验证/序列化组件； 将 ``MCPNoneAuthCredential-Input``
   替换为结构相同的
     ``MCPNoneAuthCredential`` 是组件名称修复，而不是联合删除。

6) 允许发布现有的分页限制
   - 四个搜索端点已在运行时拒绝超过 100 的限制。 他们的历史模式使用了不受支持的
   ``lte: 100`` 关键字。 将其替换为现有绑定的
   ``maximum: 100`` 文档。

7) 没有就地合同违约
   - REST 项破坏的断言更改，不是移除之前已弃用操作/属性、累加oneOf 扩展或累加响应属性
   类型宽展，都不会通过检查。 REST 客户需要 5 次版本发布的跑道，
   因此不兼容的替代品必须逐层发布或通过版本化合同发布，直到预定移除版本。

如果基线发布模式无法生成 (e.g，缺少标签/仓库问题)，脚本会发出警告并成功退出，以避免
flaky CI。
"""

from __future__ import annotations

import ast
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from packaging import version as pkg_version

from openhands.agent_server.openapi import filter_public_openapi


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_SERVER_PYPROJECT = REPO_ROOT / "openhands-agent-server" / "pyproject.toml"
PYPI_DISTRIBUTION = "openhands-agent-server"
# 将其保留在同步中，REST_ROUTE_DEPRECATION_RE 保留在 check_deprecations.py 中，以便 REST
#  破损和弃用检查识别相同的措辞。
#
REST_ROUTE_DEPRECATION_RE = re.compile(
    r"Deprecated since v(?P<deprecated>[0-9A-Za-z.+-]+)\s+"
    r"and scheduled for removal in v(?P<removed>[0-9A-Za-z.+-]+)\.?",
    re.IGNORECASE,
)
HTTP_METHODS = {
    "get",
    "put",
    "post",
    "delete",
    "patch",
    "options",
    "head",
    "trace",
}
AGENT_SERVER_REST_API_BASE_REF_ENV = "AGENT_SERVER_REST_API_BASE_REF"
RESPONSE_TYPE_WIDENING_REPORT_ENV = "AGENT_SERVER_REST_TYPE_WIDENING_REPORT_PATH"


@dataclass(frozen=True)
class ResponsePropertyTypeWidening:
    property_path: str
    added_types: str
    media_type: str
    response_status: str
    text: str


ROUTE_DECORATOR_NAMES = HTTP_METHODS | {"api_route"}
OPENAPI_PROGRAM = """
import json
import sys
from pathlib import Path

source_tree = Path(sys.argv[1])
sys.path = [
    str(source_tree / "openhands-agent-server"),
    str(source_tree / "openhands-sdk"),
    str(source_tree / "openhands-tools"),
    str(source_tree / "openhands-workspace"),
] + sys.path

from openhands.agent_server.api import create_app

print(json.dumps(create_app().openapi()))
"""


def _read_version_from_pyproject(pyproject: Path) -> str:
    data = tomllib.loads(pyproject.read_text())
    try:
        return str(data["project"]["version"])
    except KeyError as exc:  # pragma: no cover
        raise SystemExit(
            f"Unable to determine project version from {pyproject}"
        ) from exc


def _fetch_pypi_metadata(distribution: str) -> dict:
    req = urllib.request.Request(
        url=f"https://pypi.org/pypi/{distribution}/json",
        headers={"User-Agent": "openhands-agent-server-openapi-check/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def _get_baseline_version(distribution: str, current: str) -> str | None:
    try:
        meta = _fetch_pypi_metadata(distribution)
    except Exception as exc:  # pragma: no cover
        print(
            f"::warning title={distribution} REST API::Failed to fetch PyPI metadata: "
            f"{exc}"
        )
        return None

    releases = list(meta.get("releases", {}).keys())
    if not releases:
        return None

    if current in releases:
        return current

    current_parsed = pkg_version.parse(current)
    older = [rv for rv in releases if pkg_version.parse(rv) < current_parsed]
    if not older:
        return None

    return max(older, key=pkg_version.parse)


def _generate_openapi_from_source_tree(source_tree: Path, label: str) -> dict | None:
    try:
        result = subprocess.run(
            [sys.executable, "-c", OPENAPI_PROGRAM, str(source_tree)],
            check=True,
            capture_output=True,
            text=True,
            cwd=source_tree,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as exc:
        output = (exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else "")
        excerpt = output.strip()[-1000:]
        print(
            f"::warning title={PYPI_DISTRIBUTION} REST API::Failed to generate "
            f"OpenAPI schema for {label}: {exc}\n{excerpt}"
        )
        return None
    except Exception as exc:
        print(
            f"::warning title={PYPI_DISTRIBUTION} REST API::Failed to generate "
            f"OpenAPI schema for {label}: {exc}"
        )
        return None


def _generate_current_openapi() -> dict | None:
    return _generate_openapi_from_source_tree(REPO_ROOT, "current workspace")


def _generate_openapi_for_git_ref(git_ref: str) -> dict | None:
    with tempfile.TemporaryDirectory(prefix="agent-server-openapi-") as tmp:
        source_tree = Path(tmp)

        try:
            archive = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "archive", git_ref],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["tar", "-x", "-C", str(source_tree)],
                check=True,
                input=archive.stdout,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            output = (exc.stdout or b"") + (b"\n" + exc.stderr if exc.stderr else b"")
            excerpt = output.decode(errors="replace").strip()[-1000:]
            print(
                f"::warning title={PYPI_DISTRIBUTION} REST API::Failed to extract "
                f"source for {git_ref}: {exc}\n{excerpt}"
            )
            return None

        return _generate_openapi_from_source_tree(source_tree, git_ref)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is None:
            return None
        return f"{prefix}.{node.attr}"
    return None


def _find_sdk_deprecated_fastapi_routes_in_file(
    file_path: Path, repo_root: Path
) -> list[str]:
    tree = ast.parse(file_path.read_text(), filename=str(file_path))

    deprecated_names: set[str] = set()
    deprecation_module_names: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module == "openhands.sdk.utils.deprecation":
                for alias in node.names:
                    if alias.name == "deprecated":
                        deprecated_names.add(alias.asname or alias.name)
            elif node.module == "openhands.sdk.utils":
                for alias in node.names:
                    if alias.name == "deprecation":
                        deprecation_module_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "openhands.sdk.utils.deprecation":
                    deprecation_module_names.add(alias.asname or alias.name)

    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        has_route_decorator = False
        uses_sdk_deprecated = False

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            dotted_name = _dotted_name(decorator.func)
            if (
                isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in ROUTE_DECORATOR_NAMES
            ):
                has_route_decorator = True

            if dotted_name in deprecated_names or (
                dotted_name == "openhands.sdk.utils.deprecation.deprecated"
            ):
                uses_sdk_deprecated = True
                continue

            if (
                isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "deprecated"
            ):
                base_name = _dotted_name(decorator.func.value)
                if base_name in deprecation_module_names or (
                    base_name == "openhands.sdk.utils.deprecation"
                ):
                    uses_sdk_deprecated = True

        if has_route_decorator and uses_sdk_deprecated:
            rel_path = file_path.relative_to(repo_root).as_posix()
            errors.append(
                f"{rel_path}:{node.lineno} FastAPI route `{node.name}` uses "
                "openhands.sdk.utils.deprecation.deprecated; use the route "
                "decorator's deprecated=True flag instead."
            )

    return errors


def _find_sdk_deprecated_fastapi_routes(repo_root: Path) -> list[str]:
    app_root = repo_root / "openhands-agent-server" / "openhands" / "agent_server"
    errors: list[str] = []

    for file_path in sorted(app_root.rglob("*.py")):
        errors.extend(_find_sdk_deprecated_fastapi_routes_in_file(file_path, repo_root))

    return errors


def _filter_public_rest_openapi(schema: dict) -> dict:
    # 兼容性检查保留了历史组件集，因此即使在引用该路由的路线被移除后，也可以检查已批准的
    # 已弃用属性。 发布工件使用修剪的规范模式。
    #
    return filter_public_openapi(
        schema,
        prune_schemas=False,
        add_contract_components=False,
    )


def _find_deprecation_policy_errors(schema: dict) -> list[str]:
    errors: list[str] = []

    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue

        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            description = operation.get("description") or ""
            if "deprecated since" not in description.lower():
                continue

            if operation.get("deprecated") is True:
                continue

            errors.append(
                f"{method.upper()} {path} documents deprecation in its "
                "description but is not marked deprecated=true in OpenAPI."
            )

    return errors


def _parse_openapi_deprecation_description(
    description: str | None,
) -> tuple[str, str] | None:
    """从 OpenAPI 描述中提取 ``(deprecated_in, removed_in)``。

    接受的措辞有意匹配 ``check_deprecations.py``，因此两个 CI 检查都识别相同的注释，
    例如：

        Deprecated since v1.14.0 and scheduled for removal in v1.19.0.
    """
    if not description:
        return None

    match = REST_ROUTE_DEPRECATION_RE.search(" ".join(description.split()))
    if match is None:
        return None

    return match.group("deprecated").rstrip("."), match.group("removed").rstrip(".")


def _version_ge(current: str, target: str) -> bool:
    try:
        return pkg_version.parse(current) >= pkg_version.parse(target)
    except pkg_version.InvalidVersion as exc:
        raise SystemExit(
            f"Invalid semantic version comparison: {current=} {target=}"
        ) from exc


def _get_openapi_operation(schema: dict, path: str, method: str) -> dict | None:
    path_item = schema.get("paths", {}).get(path)
    if not isinstance(path_item, dict):
        return None

    operation = path_item.get(method.lower())
    if not isinstance(operation, dict):
        return None

    return operation


def _validate_removed_operations(
    removed_operations: list[dict],
    prev_schema: dict,
    current_version: str,
) -> list[str]:
    """根据基线弃用元数据验证已删除的操作。"""
    errors: list[str] = []

    for operation in removed_operations:
        path = str(operation.get("path", ""))
        method = str(operation.get("method", "")).lower()
        method_label = method.upper() or "<unknown method>"

        if not operation.get("deprecated", False):
            errors.append(
                f"Removed {method_label} {path} without prior deprecation "
                "(deprecated=true)."
            )
            continue

        baseline_operation = _get_openapi_operation(prev_schema, path, method)
        if baseline_operation is None:
            errors.append(
                f"Removed {method_label} {path} was marked deprecated in the "
                "baseline release, but the previous OpenAPI schema could not be "
                "inspected for its scheduled removal version."
            )
            continue

        deprecation_details = _parse_openapi_deprecation_description(
            baseline_operation.get("description")
        )
        if deprecation_details is None:
            errors.append(
                f"Removed {method_label} {path} was marked deprecated in the "
                "baseline release, but its OpenAPI description does not declare "
                "a scheduled removal version. REST API removals require 5 minor "
                "releases of deprecation runway."
            )
            continue

        _, removed_in = deprecation_details
        if not _version_ge(current_version, removed_in):
            errors.append(
                f"Removed {method_label} {path} before its scheduled removal "
                f"version v{removed_in} (current version: v{current_version}). "
                "REST API removals require 5 minor releases of deprecation "
                "runway."
            )
            continue

        print(
            f"::notice title={PYPI_DISTRIBUTION} REST API::Removed previously-"
            f"deprecated {method_label} {path} after its scheduled removal "
            f"version v{removed_in}."
        )

    return errors


def _iter_schema_properties(schema: dict):
    if not isinstance(schema, dict):
        return

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for property_name, property_schema in properties.items():
            if isinstance(property_schema, dict):
                yield property_name, property_schema

    for value in schema.values():
        if isinstance(value, dict):
            yield from _iter_schema_properties(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _iter_schema_properties(item)


def _removed_property_name(change: dict) -> str | None:
    text = str(change.get("text", ""))
    match = re.search(
        r"(?:request property|optional property|required property) `([^`]+)`",
        text,
    )
    if match is None:
        return None
    return match.group(1).rstrip("/").rsplit("/", maxsplit=1)[-1]


def _validate_removed_schema_properties(
    removed_properties: list[dict],
    prev_schema: dict,
    current_version: str,
) -> list[str]:
    """根据基准弃用元数据验证已删除的模式属性。"""
    errors: list[str] = []
    baseline_properties: dict[str, list[dict]] = {}
    for property_name, property_schema in _iter_schema_properties(prev_schema):
        baseline_properties.setdefault(property_name, []).append(property_schema)

    for change in removed_properties:
        property_name = _removed_property_name(change)
        if property_name is None:
            errors.append(
                "Removed schema property could not be identified from oasdiff output: "
                f"{change.get('text', str(change))}"
            )
            continue

        deprecated_candidates = [
            property_schema
            for property_schema in baseline_properties.get(property_name, [])
            if property_schema.get("deprecated") is True
        ]
        if not deprecated_candidates:
            errors.append(
                f"Removed schema property {property_name!r} without prior "
                "deprecation (deprecated=true)."
            )
            continue

        removal_targets = [
            deprecation_details[1]
            for property_schema in deprecated_candidates
            if (
                deprecation_details := _parse_openapi_deprecation_description(
                    property_schema.get("description")
                )
            )
            is not None
        ]
        if not removal_targets:
            errors.append(
                f"Removed schema property {property_name!r} was marked deprecated "
                "in the baseline release, but its OpenAPI description does not "
                "declare a scheduled removal version. REST API property removals "
                "require 5 minor releases of deprecation runway."
            )
            continue

        if not any(
            _version_ge(current_version, removed_in) for removed_in in removal_targets
        ):
            errors.append(
                f"Removed schema property {property_name!r} before its scheduled "
                f"removal version(s): {', '.join(f'v{v}' for v in removal_targets)} "
                f"(current version: v{current_version}). REST API property removals "
                "require 5 minor releases of deprecation runway."
            )
            continue

        print(
            f"::notice title={PYPI_DISTRIBUTION} REST API::Removed previously-"
            f"deprecated schema property {property_name!r} after its scheduled "
            "removal version was reached."
        )

    return errors


# oasdiff规则ID用于添加 oneOf/anyOf 回应的扩展模式。 这些被标记为 ERR 由 oasdiff 生成，
# 但被期望为可扩展的歧异组合的演化 APIs (e.g. 事件端点). 我们将它们降级为信息性通知，以
# 免它们阻断 CI.
#
_ADDITIVE_RESPONSE_ONEOF_IDS = frozenset(
    {
        "response-body-one-of-added",
        "response-property-one-of-added",
        # 将 anyOf 的变体也保留下来，这样如果 oasdiff 指出它们是破坏，加性响应-合并扩展
        # 也会得到同样的降级，而无需进一步的脚本更改。
        #
        "response-body-any-of-added",
        "response-property-any-of-added",
    }
)


_ADDITIVE_RESPONSE_BODY_ONEOF_IDS = frozenset(
    {
        "response-body-one-of-added",
        "response-body-any-of-added",
    }
)


# 响应模式中添加枚举值的 oasdiff 规则 ID。
_RESPONSE_ENUM_VALUE_ADDED_IDS = frozenset(
    {
        "response-property-enum-value-added",
        "response-write-only-property-enum-value-added",
    }
)
_RESPONSE_PROPERTY_TYPE_WIDENING_RE = re.compile(
    r"response property `(?P<property_path>[^`]+)` list-of-types was widened "
    r"by adding types `(?P<added_types>[^`]+)` to media type "
    r"`(?P<media_type>[^`]+)` of response `(?P<response_status>[^`]+)`"
)


def _parse_response_property_type_widening(
    change: dict,
) -> ResponsePropertyTypeWidening | None:
    text = str(change.get("text", ""))
    match = _RESPONSE_PROPERTY_TYPE_WIDENING_RE.search(text)
    if match is None:
        return None
    return ResponsePropertyTypeWidening(text=text, **match.groupdict())


def _is_additive_response_property_type_widening(change: dict) -> bool:
    return _parse_response_property_type_widening(change) is not None


def _response_type_widening_report_items(
    changes: list[dict],
) -> list[ResponsePropertyTypeWidening]:
    items: list[ResponsePropertyTypeWidening] = []
    for change in changes:
        widening = _parse_response_property_type_widening(change)
        if widening is not None:
            items.append(widening)
    return items


# 响应属性是已知的可扩展判别联合判别器，因此可能会累加地增长新的枚举值。 添加 HookType
# 值 (e.g. “智能体”）到钩子定义的 `type` 是安全的，因为钩子配置是一个可扩展的联合，并且
# 客户端必须容忍未知的鉴别器值。 这是有意限制在钩子标识符上的，因此，其他地方（新的状态/
# 模式等）的普通新响应值枚举仍然被视为不兼容变更。
#
_EXTENSIBLE_DISCRIMINATOR_PROPERTY_RE = re.compile(
    r"HookConfig\b.*\bhooks/items/type\b"
)
_ACCEPTED_CLOUD_PROXY_PATH_REMOVAL_ID = "api-path-removed-without-deprecation"
_ACCEPTED_CLOUD_PROXY_REMOVAL_PATH = "/api/cloud-proxy"
_ACCEPTED_CLOUD_PROXY_REMOVAL_METHOD = "post"
_ACCEPTED_CLOUD_PROXY_REMOVAL_OPERATION_ID = "cloud_proxy_api_cloud_proxy_post"

_ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_ID = "request-parameter-default-value-removed"
_ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_PATH = "/api/vscode/url"
_ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_METHOD = "get"
_ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_OPERATION_ID = (
    "get_vscode_url_api_vscode_url_get"
)
_ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_PARAM_RE = re.compile(
    r"request parameter `base_url`, default value `http://localhost:8001` "
    r"was removed"
)


def _is_accepted_vscode_base_url_default_removal(change: dict) -> bool:
    """返回 True 表示已接受的 /api/vscode/url base_url 默认删除。

    维护者在 PR #4181 中接受了这个已记录的默认删除：
    ``base_url`` 查询参数仍然保留可选性，仅服务器端回退方案改变了（从硬编码的
    ``http://localhost:8001`` 改为实际配置的
    VSCode 端口）。 ``base_url`` 项请求仍可发送，因此没有破坏客户端合同。
    """
    return (
        str(change.get("id", "")) == _ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_ID
        and str(change.get("path", ""))
        == _ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_PATH
        and str(change.get("operation", "")).lower()
        == _ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_METHOD
        and str(change.get("operationId", ""))
        == _ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_OPERATION_ID
        and bool(
            _ACCEPTED_VSCODE_BASE_URL_DEFAULT_REMOVAL_PARAM_RE.search(
                str(change.get("text", ""))
            )
        )
    )


_SEARCH_LIMIT_SCHEMA_REPAIR_PATHS = frozenset(
    {
        "/api/conversations/search",
        "/api/conversations/{conversation_id}/events/search",
        "/api/bash/bash_events/search",
        "/api/file/search_subdirs",
    }
)


def _is_search_limit_schema_repair(change: dict, prev_schema: dict) -> bool:
    """接受已知分页``lte: 100``到``maximum: 100``的修复。"""
    path = change.get("path", "")
    if (
        change.get("id") != "request-parameter-max-set"
        or path not in _SEARCH_LIMIT_SCHEMA_REPAIR_PATHS
        or str(change.get("operation", "")).lower() != "get"
        or change.get("text")
        != "for the `query` request parameter `limit`, the max was set to `100.00`"
    ):
        return False

    operation = prev_schema.get("paths", {}).get(path, {}).get("get", {})
    if change.get("operationId") != operation.get("operationId"):
        return False

    for parameter in operation.get("parameters", []):
        if parameter.get("in") == "query" and parameter.get("name") == "limit":
            schema = parameter.get("schema", {})
            return (
                schema.get("type") == "integer"
                and schema.get("lte") == 100
                and "maximum" not in schema
            )
    return False


def _is_accepted_cloud_proxy_removal(operation: dict) -> bool:
    """返回 True 以从 PR #3326 中删除已接受的 /api/cloud-proxy。"""
    path = str(operation.get("path", ""))
    method = str(operation.get("method", "")).lower()
    return (
        path == _ACCEPTED_CLOUD_PROXY_REMOVAL_PATH
        and method == _ACCEPTED_CLOUD_PROXY_REMOVAL_METHOD
        and operation.get("deprecated", False) is False
    )


def _is_accepted_cloud_proxy_path_removal(change: dict) -> bool:
    """返回 oasdiff 接受的 /api/cloud-proxy 路径移除形状的 True。"""
    return (
        str(change.get("id", "")) == _ACCEPTED_CLOUD_PROXY_PATH_REMOVAL_ID
        and str(change.get("path", "")) == _ACCEPTED_CLOUD_PROXY_REMOVAL_PATH
        and str(change.get("operation", "")).lower()
        == _ACCEPTED_CLOUD_PROXY_REMOVAL_METHOD
        and str(change.get("operationId", ""))
        == _ACCEPTED_CLOUD_PROXY_REMOVAL_OPERATION_ID
    )


def _is_additive_discriminator_enum_value(change: dict) -> bool:
    """对于已知可扩展鉴别器上的加性枚举值，返回 True。

    将值添加到响应枚举通常会破坏（生成的客户端可能会对枚举进行彻底处理），因此此功能
    仅限于钩子配置断言合集，而不是允许添加到每个响应枚举。
    """
    if str(change.get("id", "")) not in _RESPONSE_ENUM_VALUE_ADDED_IDS:
        return False
    text = str(change.get("text", ""))
    return bool(_EXTENSIBLE_DISCRIMINATOR_PROPERTY_RE.search(text))


def _is_union_property_removal_artifact(change: dict) -> bool:
    """对于作为联合扩展的工件的属性删除，返回 True。

    当请求或响应模式从一个具体的对象扩展而来模式加法 oneOf/anyOf oasdiff 可以为原始对
    象的字段生成次级“移除属性”报告，尽管 union 模式仍然作
    为联盟成员之一存在。
    """
    change_id = str(change.get("id", "")).lower()
    text = str(change.get("text", "")).lower()
    return (
        "removed" in change_id
        and "property" in change_id
        and ("from the response" in text or "request property" in text)
    )


def _is_union_type_change_artifact(change: dict) -> bool:
    text = str(change.get("text", "")).lower()
    return "type/format changed from `object`/`` to ``/``" in text


_OPAQUE_MCP_RESPONSE_REPAIR_PATHS = (
    "/mcp_config/",
    "/mcp_servers/",
    "oauth_state/",
)
_OPAQUE_TO_OBJECT_TYPE_CHANGE = (
    "response's property type/format changed from ``/`` to `object`/``"
)
_NONE_AUTH_INPUT_COMPONENT = "#/components/schemas/MCPNoneAuthCredential-Input"
_AGENT_SETTINGS_DIFF_SCHEMA_REPAIR = (
    "removed `subschema #1` from the `agent_settings_diff` request property "
    "`anyOf` list"
)


def _is_mcp_contract_schema_repair(change: dict) -> bool:
    """识别历史上不透明的电线兼容修复 MCP 模式。

    这是故意比接受任意类型更改更窄的。 响应异常仅涵盖 MCP 设置和旧模式根本没有类型的
    OAuth 状态位置。 请求异常覆盖了一个相同的Pydantic组件重命名和
    一个不受限制的对象模式的替换，该对象与具有已知字段的可扩展对象相同。
    """
    text = str(change.get("text", ""))
    if _OPAQUE_TO_OBJECT_TYPE_CHANGE in text and any(
        path in text for path in _OPAQUE_MCP_RESPONSE_REPAIR_PATHS
    ):
        return True

    if (
        text.startswith(f"removed `{_NONE_AUTH_INPUT_COMPONENT}` from the `")
        and "/auth/" in text
        and "request property `oneOf` list" in text
    ):
        return True

    return text == _AGENT_SETTINGS_DIFF_SCHEMA_REPAIR


def _split_breaking_changes(
    breaking_changes: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """将 oasdiff 结果拆分为允许列表中的存储桶和其他损坏的存储桶。"""
    removed_operations: list[dict] = []
    removed_schema_properties: list[dict] = []
    additive_response_oneof: list[dict] = []
    other_breaking_changes: list[dict] = []

    for change in breaking_changes:
        change_id = str(change.get("id", ""))
        details = change.get("details", {})

        if "removed" in change_id.lower() and "operation" in change_id.lower():
            removed_operations.append(
                {
                    "path": details.get("path", ""),
                    "method": details.get("method", ""),
                    "deprecated": details.get("deprecated", False),
                }
            )
            continue

        if "removed" in change_id.lower() and "property" in change_id.lower():
            removed_schema_properties.append(change)
            continue

        if change_id in _ADDITIVE_RESPONSE_ONEOF_IDS or (
            _is_additive_discriminator_enum_value(change)
        ):
            additive_response_oneof.append(change)
            continue

        other_breaking_changes.append(change)

    return (
        removed_operations,
        removed_schema_properties,
        additive_response_oneof,
        other_breaking_changes,
    )


def _normalize_openapi_for_oasdiff(schema: dict) -> dict:
    """标准化 OpenAPI 3.1 模式以实现 oasdiff 兼容性。

    oasdiff 需要 OpenAPI 3.0 样式 exclusiveMinimum/exclusiveMaximum 布尔值 (
    https://spec.openapis.org/oas/v3.0.3.html#schema-object )，而 OpenAPI 3.1 发出数
    值。 将数字独
    占值转换为最小/最大+独占布尔标志，以便 oasdiff 可以解析模式。

    为了方便起见，对模式进行适当的修改并返回它。
    """

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if (
                "exclusiveMinimum" in node
                and isinstance(node["exclusiveMinimum"], (int, float))
                and not isinstance(node["exclusiveMinimum"], bool)
            ):
                value = node["exclusiveMinimum"]
                if "minimum" not in node:
                    node["minimum"] = value
                node["exclusiveMinimum"] = True
            if (
                "exclusiveMaximum" in node
                and isinstance(node["exclusiveMaximum"], (int, float))
                and not isinstance(node["exclusiveMaximum"], bool)
            ):
                value = node["exclusiveMaximum"]
                if "maximum" not in node:
                    node["maximum"] = value
                node["exclusiveMaximum"] = True

            for child in node.values():
                _walk(child)
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(schema)
    return schema


def _run_oasdiff_breakage_check(
    prev_spec: Path, cur_spec: Path
) -> tuple[list[dict], int]:
    """在两个 OpenAPI 规格之间运行 oasdiff 破坏检查。

    返回（不兼容变更列表，oasdiff 的退出代码）。
    """
    try:
        result = subprocess.run(
            [
                "oasdiff",
                "breaking",
                "-f",
                "json",
                "--fail-on",
                "ERR",
                str(prev_spec),
                str(cur_spec),
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print(
            "::warning title=oasdiff not found::"
            "Please install oasdiff: https://github.com/oasdiff/oasdiff"
        )
        return [], 0

    breaking_changes = []
    if result.stdout:
        try:
            breaking_changes = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass

    return breaking_changes, result.returncode


def _find_response_property_type_widenings(
    prev_schema: dict,
    current_schema: dict,
) -> list[ResponsePropertyTypeWidening]:
    previous = _normalize_openapi_for_oasdiff(copy.deepcopy(prev_schema))
    current = _normalize_openapi_for_oasdiff(copy.deepcopy(current_schema))
    with tempfile.TemporaryDirectory(prefix="oasdiff-type-widening-") as tmp:
        tmp_path = Path(tmp)
        prev_spec_file = tmp_path / "prev_spec.json"
        cur_spec_file = tmp_path / "cur_spec.json"
        prev_spec_file.write_text(json.dumps(previous, indent=2))
        cur_spec_file.write_text(json.dumps(current, indent=2))
        breaking_changes, _ = _run_oasdiff_breakage_check(prev_spec_file, cur_spec_file)
    return _response_type_widening_report_items(breaking_changes)


def _collect_response_property_type_widenings_since_ref(
    base_ref: str,
    current_schema: dict,
) -> list[ResponsePropertyTypeWidening] | None:
    base_schema = _generate_openapi_for_git_ref(base_ref)
    if base_schema is None:
        return None
    base_schema = _filter_public_rest_openapi(base_schema)
    return _find_response_property_type_widenings(base_schema, current_schema)


def _write_response_type_widening_report(
    changes: list[ResponsePropertyTypeWidening],
    *,
    changes_since_base: list[ResponsePropertyTypeWidening] | None = None,
) -> None:
    report_path = os.environ.get(RESPONSE_TYPE_WIDENING_REPORT_ENV, "").strip()
    if not report_path:
        return

    report = {
        "additive_response_property_type_widenings": [
            asdict(change) for change in changes
        ]
    }
    if changes_since_base is not None:
        report["additive_response_property_type_widenings_since_base"] = [
            asdict(change) for change in changes_since_base
        ]

    Path(report_path).write_text(json.dumps(report, indent=2) + "\n")


def main() -> int:
    current_version = _read_version_from_pyproject(AGENT_SERVER_PYPROJECT)
    baseline_version = _get_baseline_version(PYPI_DISTRIBUTION, current_version)

    if baseline_version is None:
        print(
            f"::warning title={PYPI_DISTRIBUTION} REST API::Unable to find baseline "
            f"version for {current_version}; skipping breakage checks."
        )
        return 0

    baseline_git_ref = f"v{baseline_version}"

    static_policy_errors = _find_sdk_deprecated_fastapi_routes(REPO_ROOT)
    for error in static_policy_errors:
        print(f"::error title={PYPI_DISTRIBUTION} REST API::{error}")

    current_schema = _generate_current_openapi()
    if current_schema is None:
        return 1
    current_schema = _filter_public_rest_openapi(current_schema)

    deprecation_policy_errors = _find_deprecation_policy_errors(current_schema)
    for error in deprecation_policy_errors:
        print(f"::error title={PYPI_DISTRIBUTION} REST API::{error}")

    prev_schema = _generate_openapi_for_git_ref(baseline_git_ref)
    if prev_schema is None:
        return 0 if not (static_policy_errors or deprecation_policy_errors) else 1
    prev_schema = _filter_public_rest_openapi(prev_schema)

    prev_schema = _normalize_openapi_for_oasdiff(prev_schema)
    current_schema = _normalize_openapi_for_oasdiff(current_schema)

    with tempfile.TemporaryDirectory(prefix="oasdiff-specs-") as tmp:
        tmp_path = Path(tmp)
        prev_spec_file = tmp_path / "prev_spec.json"
        cur_spec_file = tmp_path / "cur_spec.json"
        prev_spec_file.write_text(json.dumps(prev_schema, indent=2))
        cur_spec_file.write_text(json.dumps(current_schema, indent=2))

        breaking_changes, exit_code = _run_oasdiff_breakage_check(
            prev_spec_file, cur_spec_file
        )

    response_type_widenings: list[ResponsePropertyTypeWidening] = []
    response_type_widenings_since_base: list[ResponsePropertyTypeWidening] | None = None
    report_path = os.environ.get(RESPONSE_TYPE_WIDENING_REPORT_ENV, "").strip()
    base_ref = os.environ.get(AGENT_SERVER_REST_API_BASE_REF_ENV, "").strip()
    if report_path and base_ref:
        response_type_widenings_since_base = (
            _collect_response_property_type_widenings_since_ref(
                base_ref, current_schema
            )
        )

    if not breaking_changes:
        if exit_code == 0:
            print("No breaking changes detected.")
        else:
            print(
                f"oasdiff returned exit code {exit_code} but no breaking changes "
                "in JSON format. There may be warnings only."
            )
        _write_response_type_widening_report(
            response_type_widenings,
            changes_since_base=response_type_widenings_since_base,
        )

    else:
        (
            removed_operations,
            removed_schema_properties,
            additive_response_oneof,
            other_breaking_changes,
        ) = _split_breaking_changes(breaking_changes)
        response_union_artifacts = [
            change
            for change in removed_schema_properties
            if _is_union_property_removal_artifact(change)
        ]
        removed_schema_properties = [
            change
            for change in removed_schema_properties
            if not _is_union_property_removal_artifact(change)
        ]
        union_type_artifacts = [
            change
            for change in other_breaking_changes
            if _is_union_type_change_artifact(change)
        ]
        other_breaking_changes = [
            change
            for change in other_breaking_changes
            if not _is_union_type_change_artifact(change)
        ]
        mcp_contract_schema_repairs = [
            change
            for change in other_breaking_changes
            if _is_mcp_contract_schema_repair(change)
        ]
        other_breaking_changes = [
            change
            for change in other_breaking_changes
            if not _is_mcp_contract_schema_repair(change)
        ]
        accepted_response_type_widening_changes = [
            change
            for change in other_breaking_changes
            if _is_additive_response_property_type_widening(change)
        ]
        other_breaking_changes = [
            change
            for change in other_breaking_changes
            if not _is_additive_response_property_type_widening(change)
        ]
        response_type_widenings = _response_type_widening_report_items(
            accepted_response_type_widening_changes
        )

        accepted_cloud_proxy_removals = [
            operation
            for operation in removed_operations
            if _is_accepted_cloud_proxy_removal(operation)
        ]
        removed_operations = [
            operation
            for operation in removed_operations
            if not _is_accepted_cloud_proxy_removal(operation)
        ]
        accepted_cloud_proxy_path_removals = [
            change
            for change in other_breaking_changes
            if _is_accepted_cloud_proxy_path_removal(change)
        ]
        other_breaking_changes = [
            change
            for change in other_breaking_changes
            if not _is_accepted_cloud_proxy_path_removal(change)
        ]
        accepted_vscode_base_url_default_removals = [
            change
            for change in other_breaking_changes
            if _is_accepted_vscode_base_url_default_removal(change)
        ]
        other_breaking_changes = [
            change
            for change in other_breaking_changes
            if not _is_accepted_vscode_base_url_default_removal(change)
        ]
        search_limit_schema_repairs = [
            change
            for change in other_breaking_changes
            if _is_search_limit_schema_repair(change, prev_schema)
        ]
        other_breaking_changes = [
            change
            for change in other_breaking_changes
            if not _is_search_limit_schema_repair(change, prev_schema)
        ]

        removal_errors = _validate_removed_operations(
            removed_operations,
            prev_schema,
            current_version,
        )
        property_removal_errors = _validate_removed_schema_properties(
            removed_schema_properties,
            prev_schema,
            current_version,
        )

        for error in removal_errors + property_removal_errors:
            print(f"::error title={PYPI_DISTRIBUTION} REST API::{error}")

        if accepted_cloud_proxy_removals or accepted_cloud_proxy_path_removals:
            print(
                f"\n::notice title={PYPI_DISTRIBUTION} REST API::"
                "Accepted removal of POST /api/cloud-proxy. Maintainers "
                "explicitly accepted this REST break in PR #3326, and that PR "
                "is labeled release-note-required."
            )

        if accepted_vscode_base_url_default_removals:
            print(
                f"\n::notice title={PYPI_DISTRIBUTION} REST API::"
                "Accepted removal of the documented default for the optional "
                "`base_url` query parameter of GET /api/vscode/url (PR #4181). "
                "The parameter stays optional; only the server-side fallback "
                "changed, so requests that omit it keep working."
            )

        if search_limit_schema_repairs:
            print(
                f"\n::notice title={PYPI_DISTRIBUTION} REST API::"
                "Published the existing search limit of 100 by correcting "
                "legacy lte metadata to maximum."
            )
            for item in search_limit_schema_repairs:
                print(f"  - GET {item['path']}: {item['text']}")

        if additive_response_oneof:
            print(
                f"\n::notice title={PYPI_DISTRIBUTION} REST API::"
                "Additive oneOf/anyOf expansion or enum-value additions detected "
                "in response schemas. This is expected for extensible "
                "discriminated-union APIs and does not break backward "
                "compatibility."
            )
            for item in additive_response_oneof:
                print(f"  - {item.get('text', str(item))}")
            if response_union_artifacts:
                print(
                    "  - ignored "
                    f"{len(response_union_artifacts)} request/response-property "
                    "removal artifact(s) caused by union widening"
                )
            if union_type_artifacts:
                print(
                    "  - ignored "
                    f"{len(union_type_artifacts)} request/response type-change "
                    "artifact(s) caused by union widening"
                )

        if response_type_widenings:
            print(
                f"\n::notice title={PYPI_DISTRIBUTION} REST API::"
                "Additive response property type widenings detected. The previous "
                "type remains valid, so these changes are accepted with a "
                "release-note-required label."
            )
            for item in response_type_widenings:
                print(f"  - {item.text}")

        if mcp_contract_schema_repairs:
            print(
                f"\n::notice title={PYPI_DISTRIBUTION} REST API::"
                "Typed historically opaque MCP/settings schemas without changing "
                "their runtime wire format."
            )
            for item in mcp_contract_schema_repairs:
                print(f"  - {item.get('text', str(item))}")

        if other_breaking_changes:
            print(
                "::error "
                f"title={PYPI_DISTRIBUTION} REST API::Detected breaking REST API "
                "changes other than removing previously-deprecated operations/"
                "properties, additive response oneOf expansions, or additive "
                "response property type widenings. "
                "REST contract changes must preserve compatibility for 5 minor "
                "releases; keep the old contract available until its scheduled "
                "removal version."
            )
        elif (
            response_union_artifacts or union_type_artifacts
        ) and not additive_response_oneof:
            print(
                f"\n::notice title={PYPI_DISTRIBUTION} REST API::"
                f"Ignored {len(response_union_artifacts)} property-removal and "
                f"{len(union_type_artifacts)} type-change artifact(s) reported "
                "while widening schemas."
            )

        print("\nBreaking REST API changes detected compared to baseline release:")
        for text in breaking_changes:
            print(f"- {text.get('text', str(text))}")

        _write_response_type_widening_report(
            response_type_widenings,
            changes_since_base=response_type_widenings_since_base,
        )

        if not (removal_errors or property_removal_errors or other_breaking_changes):
            print(
                "Breaking changes are limited to previously-deprecated operations "
                "or properties whose scheduled removal versions have been reached, "
                "the accepted POST /api/cloud-proxy removal, the accepted "
                "GET /api/vscode/url base_url default removal, additive response "
                "oneOf expansions, and/or additive response property type widenings."
                " It may also include wire-compatible repairs of historically "
                "opaque MCP/settings schemas or the existing search limit of 100."
            )
        else:
            return 1

    return 1 if (static_policy_errors or deprecation_policy_errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
