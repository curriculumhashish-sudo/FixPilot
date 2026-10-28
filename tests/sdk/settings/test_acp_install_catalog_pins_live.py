"""实时可安装性检查 ACP_INSTALL_CATALOG 固定的 npm 版本。

针对真实的 npm 注册表运行 ``npm view <pkg>@<version>``，因此此处捕获了拉出的版本或安
全性弃用，而不是破坏下一个智能体服务器映像构建。 凭据
-免费； 需要 ``npm`` 和对注册表的网络访问（不可用时跳过）。 参见OpenHands/软件-智能体
-SDK#4830 P0-3。

通过 ``acp_live`` 标记取消选择默认运行（请参阅
``tests/sdk/agent/test_acp_conformance.py`` 原因）：SDK 的默认测试作业是必需的合并检
查，并且实时注册表依赖项必须无法阻止不相
关的 PR。 使用 ``pytest -m acp_live`` 显式运行； CI 在单独的、非必需的
``acp-live-tests`` 作业中运行它。
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess

import pytest

from openhands.sdk.settings.acp_install_catalog import ACP_INSTALL_CATALOG


def _npm_registry_reachable(timeout: float = 3.0) -> bool:
    try:
        socket.create_connection(("registry.npmjs.org", 443), timeout=timeout).close()
        return True
    except OSError:
        return False


requires_npm = pytest.mark.skipif(
    shutil.which("npm") is None or not _npm_registry_reachable(),
    reason="npm not available, or npm registry unreachable",
)

pytestmark = pytest.mark.acp_live

_ALL_PINS = [
    pytest.param(spec.key, pkg.name, pkg.version, id=f"{spec.key}:{pkg.pinned}")
    for spec in ACP_INSTALL_CATALOG.values()
    for pkg in spec.packages
]


def _npm_view_version_deprecated(pinned: str) -> tuple[str, str | None]:
    """返回 ``(resolved_version, deprecation_message_or_None)`` 表示
    ``name@version`` npm 规范，如果无法解决（被拉出、拼写错误、从未发布），则提出
    ``AssertionError``。
    """
    result = subprocess.run(
        ["npm", "view", pinned, "version", "deprecated", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"npm view {pinned!r} produced unparseable output "
            f"(exit={result.returncode}): stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        ) from None
    if isinstance(data, dict) and "error" in data:
        raise AssertionError(f"npm view {pinned!r} failed: {data['error']}")
    if isinstance(data, str):
        return data, None
    return data["version"], data.get("deprecated")


@requires_npm
@pytest.mark.parametrize("provider_key,package_name,pinned_version", _ALL_PINS)
def test_pinned_version_resolves_and_is_not_deprecated(
    provider_key: str, package_name: str, pinned_version: str
) -> None:
    pinned = f"{package_name}@{pinned_version}"
    resolved_version, deprecated = _npm_view_version_deprecated(pinned)
    assert resolved_version == pinned_version, (
        f"npm resolved {pinned!r} to version {resolved_version!r}, expected "
        f"{pinned_version!r} — the registry's tag resolution disagrees with "
        "the exact pin"
    )
    assert deprecated is None, (
        f"{pinned!r} (provider={provider_key}) is deprecated on npm: "
        f"{deprecated!r} — bump ACP_INSTALL_CATALOG to a non-deprecated version"
    )


def _npm_view_bins(pinned: str) -> set[str]:
    """返回 ``name@version`` 在其 ``bin`` 字段中声明的可执行文件名称。

    npm accepts either a string (one bin, named after the package) or an
    将 bin 名称映射到路径的对象。
    """
    result = subprocess.run(
        ["npm", "view", pinned, "bin", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if not result.stdout.strip():
        return set()
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"npm view {pinned!r} bin produced unparseable output "
            f"(exit={result.returncode}): stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        ) from None
    if isinstance(data, dict):
        return set(data)
    if isinstance(data, str):
        return {pinned.rsplit("@", 1)[0].rsplit("/", 1)[-1]}
    return set()


@requires_npm
@pytest.mark.parametrize(
    "spec", ACP_INSTALL_CATALOG.values(), ids=list(ACP_INSTALL_CATALOG)
)
def test_binary_name_is_declared_by_one_of_the_pinned_packages(spec) -> None:
    """``binary_name`` 必须是某个固定包实际声明的 bin。

    该图像构建的自护机制仅覆盖给定构建安装的提供者，所以注册表-仅提供者
    ``binary_name`` 它在其他地方也没有被验证过——一个错误的版本就会悄悄地失去固定
    二进制路径``resolve_acp_command`` 或者，当预先安装时，它会提供一个指向空的包装器
    。
    """
    declared: set[str] = set()
    for pkg in spec.packages:
        declared |= _npm_view_bins(pkg.pinned)
    assert spec.binary_name in declared, (
        f"{spec.key}: binary_name {spec.binary_name!r} is not declared by any "
        f"pinned package; npm reports {sorted(declared)} for "
        f"{[p.pinned for p in spec.packages]}"
    )
