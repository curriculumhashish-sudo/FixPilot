"""入口遏制的对抗性测试（安全关键）。

与通用的ifest文件分开管理验证这些测试涉及文件系统级别的检查 ``resolve_entrypoint`` (
路径遍历和符号链接逃逸)，而不是语法
``entrypoint`` field 验证器。
"""

from pathlib import Path

import pytest

from openhands.agent_server.canvas_extensions.manifest import (
    CanvasExtensionManifest,
    resolve_entrypoint,
)


def _manifest_with_raw_entrypoint(entrypoint: str) -> CanvasExtensionManifest:
    """构建绕过字段的清单验证。

    让这些测试直接用入口驱动 ``resolve_entrypoint``，语法验证器在构造时已经被拒绝。
    """
    manifest = CanvasExtensionManifest(
        schema_version=1,
        name="my-extension",
        display_name="My Extension",
        version="1.0.0",
        entrypoint="index.js",
    )
    return manifest.model_copy(update={"entrypoint": entrypoint})


@pytest.fixture
def package_root(tmp_path: Path) -> Path:
    root = tmp_path / "installed" / "my-extension"
    root.mkdir(parents=True)
    (root / "index.js").write_text("console.log('ok')")
    return root


def test_resolves_valid_entrypoint(package_root: Path):
    manifest = _manifest_with_raw_entrypoint("index.js")
    resolved = resolve_entrypoint(manifest, package_root)
    assert resolved == (package_root / "index.js").resolve()


def test_resolves_valid_nested_entrypoint(package_root: Path):
    (package_root / "dist").mkdir()
    (package_root / "dist" / "bundle.js").write_text("console.log('ok')")
    manifest = _manifest_with_raw_entrypoint("dist/bundle.js")
    resolved = resolve_entrypoint(manifest, package_root)
    assert resolved == (package_root / "dist" / "bundle.js").resolve()


def test_resolves_entrypoint_via_in_package_symlink(package_root: Path):
    """位于 ``package_root`` 内的符号链接是合法的 (e.g. 建造
    工具）并且仍然必须解决——只有转义被拒绝。
    """
    (package_root / "dist").mkdir()
    real_bundle = package_root / "dist" / "bundle.js"
    real_bundle.write_text("console.log('ok')")
    (package_root / "index.js").unlink()
    (package_root / "index.js").symlink_to(real_bundle)

    manifest = _manifest_with_raw_entrypoint("index.js")
    resolved = resolve_entrypoint(manifest, package_root)
    assert resolved == real_bundle.resolve()


@pytest.mark.parametrize(
    "entrypoint",
    [
        "../../../../etc/passwd",
        "../sibling-package/index.js",
        "dist/../../escape.js",
        "a/b/c/../../../../../../etc/passwd",
    ],
)
def test_rejects_textual_traversal_escape(package_root: Path, entrypoint: str):
    manifest = _manifest_with_raw_entrypoint(entrypoint)
    with pytest.raises(ValueError, match="resolves outside"):
        resolve_entrypoint(manifest, package_root)


def test_rejects_absolute_entrypoint_bypassing_field_validation(
    package_root: Path, tmp_path: Path
):
    """``root / "/abs/path"``默默地丢弃``root``（一个众所周知的
    pathlib footgun：使用绝对路径连接会将所有内容删除到其左侧，与 ``os.path.join`` 相
    同）。 确认包含仍然捕获这个值，而不是信任连接，因
    为一个入口值到达 ``resolve_entrypoint`` 但没有经过字段验证（通常会首先拒绝绝对路
    径）。
    """
    outside_secret = tmp_path / "outside-secret.js"
    outside_secret.write_text("should never be served")
    assert (package_root / str(outside_secret)) == outside_secret  # 步枪

    manifest = _manifest_with_raw_entrypoint(str(outside_secret))
    with pytest.raises(ValueError, match="resolves outside"):
        resolve_entrypoint(manifest, package_root)


def test_rejects_symlinked_file_escaping_root(package_root: Path, tmp_path: Path):
    outside_secret = tmp_path / "outside-secret.js"
    outside_secret.write_text("should never be served")

    escape_link = package_root / "index.js"
    escape_link.unlink()
    escape_link.symlink_to(outside_secret)

    manifest = _manifest_with_raw_entrypoint("index.js")
    with pytest.raises(ValueError, match="resolves outside"):
        resolve_entrypoint(manifest, package_root)


def test_rejects_symlinked_directory_escaping_root(package_root: Path, tmp_path: Path):
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "payload.js").write_text("should never be served")

    (package_root / "linked").symlink_to(outside_dir, target_is_directory=True)

    manifest = _manifest_with_raw_entrypoint("linked/payload.js")
    with pytest.raises(ValueError, match="resolves outside"):
        resolve_entrypoint(manifest, package_root)


def test_rejects_symlinked_package_root_itself(package_root: Path, tmp_path: Path):
    """符号链接的 ``package_root`` 仍应将分辨率限制为其目标。"""
    outside_secret = tmp_path / "outside-secret.js"
    outside_secret.write_text("should never be served")

    real_root = tmp_path / "real-root"
    real_root.mkdir()
    (real_root / "index.js").write_text("console.log('ok')")
    (real_root / "escape").symlink_to(outside_secret)

    aliased_root = tmp_path / "aliased-root"
    aliased_root.symlink_to(real_root, target_is_directory=True)

    manifest = _manifest_with_raw_entrypoint("escape")
    with pytest.raises(ValueError, match="resolves outside"):
        resolve_entrypoint(manifest, aliased_root)


def test_rejects_entrypoint_equal_to_package_root(package_root: Path):
    """``.`` 被包含（没有转义），但它是一个目录，而不是入口。"""
    manifest = _manifest_with_raw_entrypoint(".")
    with pytest.raises(ValueError, match="does not resolve to a file"):
        resolve_entrypoint(manifest, package_root)


def test_rejects_entrypoint_pointing_at_a_directory(package_root: Path):
    (package_root / "dist").mkdir()
    manifest = _manifest_with_raw_entrypoint("dist")
    with pytest.raises(ValueError, match="does not resolve to a file"):
        resolve_entrypoint(manifest, package_root)


def test_rejects_missing_entrypoint(package_root: Path):
    manifest = _manifest_with_raw_entrypoint("does-not-exist.js")
    with pytest.raises(ValueError, match="does not resolve to a file"):
        resolve_entrypoint(manifest, package_root)


def test_rejects_symlink_cycle(package_root: Path):
    """自引用符号链接必须 resolve() 干净，不会挂起或崩溃，
    并且仍然必须被拒绝，因为它永远不会解析为真实文件。
    """
    loop = package_root / "index.js"
    loop.unlink()
    loop.symlink_to(loop)

    manifest = _manifest_with_raw_entrypoint("index.js")
    with pytest.raises(ValueError, match="does not resolve to a file"):
        resolve_entrypoint(manifest, package_root)
