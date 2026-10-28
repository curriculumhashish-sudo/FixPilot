import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from openhands.sdk.extensions.fetch import ExtensionFetchError
from openhands.sdk.extensions.installation import (
    InstallationInterface,
    InstallationManager,
    InstallationMetadata,
)


class MockExtension(BaseModel):
    name: str
    version: str
    description: str


class MockExtensionInstallationInterface(InstallationInterface):
    @staticmethod
    def load_from_dir(extension_dir: Path) -> MockExtension:
        return MockExtension.model_validate_json(
            (extension_dir / "extension.json").read_text()
        )


def _write_mock_extension(
    directory: Path,
    name: str = "mock-extension",
    version: str = "0.0.1",
    description: str = "Mock extension",
) -> Path:
    """将模拟对象扩展清单写入目录。"""
    directory.mkdir(parents=True, exist_ok=True)
    ext = MockExtension(name=name, version=version, description=description)
    with (directory / "extension.json").open("w") as f:
        f.write(ext.model_dump_json())
    return directory


@pytest.fixture
def mock_extension() -> MockExtension:
    """构建模拟对象扩展类的实例。"""
    return MockExtension(
        name="mock-extension", version="0.0.1", description="Mock extension"
    )


@pytest.fixture
def mock_extension_dir(mock_extension: MockExtension, tmp_path: Path) -> Path:
    """为模拟对象扩展构建一个临时目录，可使用以下命令加载
    `load_from_dir` 功能。
    """
    return _write_mock_extension(
        tmp_path / "mock-extension",
        name=mock_extension.name,
        version=mock_extension.version,
        description=mock_extension.description,
    )


@pytest.fixture
def installation_dir(tmp_path: Path) -> Path:
    """构建安装目录。"""
    installation_dir: Path = tmp_path / "installed"
    installation_dir.mkdir(parents=True, exist_ok=True)
    return installation_dir


@pytest.fixture
def manager(installation_dir: Path) -> InstallationManager[MockExtension]:
    """使用模拟对象接口构建 InstallationManager。"""
    return InstallationManager(
        installation_dir=installation_dir,
        installation_interface=MockExtensionInstallationInterface(),
    )


# ============================================================================
# 安装测试
# ============================================================================


def test_install_from_local_path(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    installation_dir: Path,
    mock_extension: MockExtension,
):
    """可以从本地源安装测试扩展。"""
    extension_info = manager.install(str(mock_extension_dir))

    assert extension_info.name == mock_extension.name
    assert extension_info.version == mock_extension.version
    assert extension_info.description == mock_extension.description

    extension_dir = installation_dir / mock_extension.name
    assert extension_dir.exists()
    assert (extension_dir / "extension.json").exists()

    metadata = InstallationMetadata.load_from_dir(installation_dir)
    assert mock_extension.name in metadata.extensions


def test_install_records_requested_ref(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试传递给install()的ref是否被记录为requested_ref，
    与已解决的提交 SHA 分开。"""
    with patch(
        "openhands.sdk.extensions.installation.manager.fetch_with_resolution",
        return_value=(mock_extension_dir, "abc123"),
    ):
        info = manager.install(source="github:org/repo", ref="v1.0.0")

    assert info.requested_ref == "v1.0.0"
    assert info.resolved_ref == "abc123"


def test_install_without_ref_leaves_requested_ref_none(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试省略 ref 是否会使 requested_ref 未设置，即使
    resolved_ref 仍然被记录（跟踪移动的参考）。"""
    with patch(
        "openhands.sdk.extensions.installation.manager.fetch_with_resolution",
        return_value=(mock_extension_dir, "abc123"),
    ):
        info = manager.install(source="github:org/repo")

    assert info.requested_ref is None
    assert info.resolved_ref == "abc123"


def test_update_reclones_with_credentialed_source(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    mock_extension: MockExtension,
):
    """update() 使用 .installed.json 中记录的真实凭据重新克隆。

    扩展没有${VAR}机制，并且扩展层没有密码，因此源在REST处保持完整； 在这里进行编辑会
    使私有扩展无法在更新时重新克隆（回归问题 #3752 的防护）。
    """
    cred = "https://oauth2:SUPER_SECRET@github.com/org/repo.git"
    with patch(
        "openhands.sdk.extensions.installation.manager.fetch_with_resolution",
        return_value=(mock_extension_dir, "abc123"),
    ) as mock_fetch:
        manager.install(source=cred, force=True)  # 在 .installed.json 中记录信用
        mock_fetch.reset_mock()
        manager.update(mock_extension.name)  # 从存储的源中重新获取

    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.kwargs["source"] == cred


def test_install_already_exist_raises_error(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试安装现有扩展是否会引发 FileExistsError。"""
    manager.install(mock_extension_dir)

    with pytest.raises(FileExistsError):
        manager.install(mock_extension_dir)

    assert manager.install(mock_extension_dir, force=True)


def test_install_with_force_overwrites(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    installation_dir: Path,
    mock_extension: MockExtension,
):
    """测试force=True是否覆盖现有安装。"""
    manager.install(mock_extension_dir)

    marker_file = installation_dir / mock_extension.name / "marker.txt"
    marker_file.write_text("MARK")
    assert marker_file.exists()

    manager.install(mock_extension_dir, force=True)

    assert not marker_file.exists()


def test_failed_force_git_install_preserves_files_and_metadata(
    manager: InstallationManager[MockExtension],
    installation_dir: Path,
    mock_extension: MockExtension,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = _write_mock_extension(tmp_path / "source")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=source,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    subprocess.run(["git", "config", "commit.gpgSign", "false"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=source, check=True)
    monkeypatch.setattr(
        "openhands.sdk.extensions.installation.manager.DEFAULT_CACHE_DIR",
        tmp_path / "cache",
    )
    source_url = f"file://{source}"
    manager.install(source_url)

    installed_dir = installation_dir / mock_extension.name
    manifest_path = installed_dir / "extension.json"
    manifest_before = manifest_path.read_bytes()
    marker_file = installed_dir / "marker.txt"
    marker_file.write_text("original")
    metadata_path = installation_dir / ".installed.json"
    metadata_before = metadata_path.read_bytes()

    with pytest.raises(ExtensionFetchError, match="Failed to fetch extension"):
        manager.install(source=source_url, ref="missing-ref", force=True)

    assert marker_file.read_text() == "original"
    assert manifest_path.read_bytes() == manifest_before
    assert metadata_path.read_bytes() == metadata_before


def test_install_invalid_extension_name_raises_error(
    manager: InstallationManager[MockExtension],
    tmp_path: Path,
):
    """测试安装具有无效清单名称的扩展是否失败。"""
    bad_dir = _write_mock_extension(tmp_path / "bad-ext", name="bad_name")

    with pytest.raises(ValueError, match="Invalid extension name"):
        manager.install(str(bad_dir))


def test_install_force_preserves_enabled_state(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试强制重新安装是否保留现有的启用状态。"""
    manager.install(str(mock_extension_dir))
    manager.disable("mock-extension")

    info = manager.install(mock_extension_dir, force=True)

    assert info.enabled is False


# ============================================================================
# 卸载测试
# ============================================================================


def test_uninstall_existing_extension(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    installation_dir: Path,
):
    """测试卸载现有扩展。"""
    manager.install(str(mock_extension_dir))

    result = manager.uninstall("mock-extension")

    assert result is True
    assert not (installation_dir / "mock-extension").exists()

    metadata = InstallationMetadata.load_from_dir(installation_dir)
    assert "mock-extension" not in metadata.extensions


def test_uninstall_nonexistent_extension(
    manager: InstallationManager[MockExtension],
):
    """测试卸载不存在的扩展。"""
    result = manager.uninstall("nonexistent")
    assert result is False


def test_uninstall_untracked_extension_does_not_delete(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    installation_dir: Path,
):
    """测试卸载拒绝删除未跟踪的扩展目录。"""
    dest = installation_dir / "untracked-ext"
    shutil.copytree(mock_extension_dir, dest)

    # 重写清单，使名称与目录匹配
    _write_mock_extension(dest, name="untracked-ext")

    result = manager.uninstall("untracked-ext")

    assert result is False
    assert dest.exists()


def test_uninstall_tracked_but_directory_missing(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    installation_dir: Path,
):
    """测试跟踪时卸载是否成功，但目录已被删除。"""
    manager.install(str(mock_extension_dir))
    shutil.rmtree(installation_dir / "mock-extension")

    result = manager.uninstall("mock-extension")

    assert result is True
    metadata = InstallationMetadata.load_from_dir(installation_dir)
    assert "mock-extension" not in metadata.extensions


def test_uninstall_invalid_name_raises_error(
    manager: InstallationManager[MockExtension],
):
    """测试无效的扩展名是否被拒绝。"""
    with pytest.raises(ValueError, match="Invalid extension name"):
        manager.uninstall("../evil")


# ============================================================================
# 列出已安装的测试
# ============================================================================


def test_list_nonexistent_installation_dir(tmp_path: Path):
    """当 installation_dir 不存在时测试列表返回空。"""
    manager = InstallationManager(
        installation_dir=tmp_path / "does-not-exist",
        installation_interface=MockExtensionInstallationInterface(),
    )
    assert manager.list_installed() == []


def test_list_empty_directory(
    manager: InstallationManager[MockExtension],
):
    """测试列出空目录中的扩展。"""
    extensions = manager.list_installed()
    assert extensions == []


def test_list_installed_extensions(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试列出已安装的扩展。"""
    manager.install(str(mock_extension_dir))

    extensions = manager.list_installed()

    assert len(extensions) == 1
    assert extensions[0].name == "mock-extension"
    assert extensions[0].version == "0.0.1"


def test_list_discovers_untracked_extensions(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    installation_dir: Path,
):
    """测试该列表是否发现元数据中没有的扩展。"""
    dest = installation_dir / "manual-ext"
    shutil.copytree(mock_extension_dir, dest)
    _write_mock_extension(dest, name="manual-ext")

    extensions = manager.list_installed()

    assert len(extensions) == 1
    assert extensions[0].name == "manual-ext"
    assert extensions[0].source == "local"


def test_list_cleans_up_missing_extensions(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    installation_dir: Path,
):
    """测试该列表删除丢失扩展的元数据。"""
    manager.install(str(mock_extension_dir))

    shutil.rmtree(installation_dir / "mock-extension")

    extensions = manager.list_installed()

    assert len(extensions) == 0
    metadata = InstallationMetadata.load_from_dir(installation_dir)
    assert "mock-extension" not in metadata.extensions


# ============================================================================
# 加载已安装的测试
# ============================================================================


def test_load_nonexistent_installation_dir(tmp_path: Path):
    """当 installation_dir 不存在时测试加载返回空。"""
    manager = InstallationManager(
        installation_dir=tmp_path / "does-not-exist",
        installation_interface=MockExtensionInstallationInterface(),
    )
    assert manager.load_installed() == []


def test_load_empty_directory(
    manager: InstallationManager[MockExtension],
):
    """测试从空目录加载扩展。"""
    extensions = manager.load_installed()
    assert extensions == []


def test_load_installed_extensions(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试加载已安装的扩展。"""
    manager.install(str(mock_extension_dir))

    extensions = manager.load_installed()

    assert len(extensions) == 1
    assert extensions[0].name == "mock-extension"


def test_disable_extension_filters_load(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试禁用的扩展是否被排除在负载之外。"""
    manager.install(str(mock_extension_dir))

    assert manager.disable("mock-extension") is True

    extensions = manager.load_installed()
    assert extensions == []

    info = manager.get("mock-extension")
    assert info is not None
    assert info.enabled is False


def test_enable_extension_restores_load(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试重新启用的扩展是否再次加载。"""
    manager.install(str(mock_extension_dir))
    manager.disable("mock-extension")

    assert manager.enable("mock-extension") is True

    extensions = manager.load_installed()
    assert len(extensions) == 1
    assert extensions[0].name == "mock-extension"


def test_enable_nonexistent_extension_returns_false(
    manager: InstallationManager[MockExtension],
):
    """测试启用不存在的扩展会返回 False。"""
    assert manager.enable("nonexistent") is False


def test_disable_nonexistent_extension_returns_false(
    manager: InstallationManager[MockExtension],
):
    """测试禁用不存在的扩展会返回 False。"""
    assert manager.disable("nonexistent") is False


# ============================================================================
# 获取扩展测试
# ============================================================================


def test_get_existing_extension(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试获取现有扩展的信息。"""
    manager.install(str(mock_extension_dir))

    info = manager.get("mock-extension")

    assert info is not None
    assert info.name == "mock-extension"


def test_get_nonexistent_extension(
    manager: InstallationManager[MockExtension],
):
    """测试获取不存在的扩展程序的信息。"""
    info = manager.get("nonexistent")
    assert info is None


def test_get_extension_with_missing_directory(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
    installation_dir: Path,
):
    """测试扩展目录丢失时获取信息。"""
    manager.install(str(mock_extension_dir))

    shutil.rmtree(installation_dir / "mock-extension")

    info = manager.get("mock-extension")
    assert info is None


# ============================================================================
# 更新扩展测试
# ============================================================================


def test_update_existing_extension_local(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """测试从本地源更新已安装的扩展。"""
    manager.install(str(mock_extension_dir))
    manager.disable("mock-extension")

    # 修改源码为新版本
    _write_mock_extension(
        mock_extension_dir,
        name="mock-extension",
        version="0.0.2",
        description="Updated extension",
    )

    updated = manager.update("mock-extension")

    assert updated is not None
    assert updated.version == "0.0.2"
    assert updated.enabled is False


def test_update_nonexistent_extension(
    manager: InstallationManager[MockExtension],
):
    """测试更新不存在的扩展。"""
    info = manager.update("nonexistent")
    assert info is None


def test_update_clears_requested_ref_to_track_latest(
    manager: InstallationManager[MockExtension],
    mock_extension_dir: Path,
):
    """update() 使用 ref=None 重新获取，因此之前固定的 requested_ref
    被清除以反映该扩展现在跟踪最新版本。"""
    with patch(
        "openhands.sdk.extensions.installation.manager.fetch_with_resolution",
        return_value=(mock_extension_dir, "abc123"),
    ) as mock_fetch:
        info = manager.install(source="github:org/repo", ref="v1.0.0")
        assert info.requested_ref == "v1.0.0"

        mock_fetch.return_value = (mock_extension_dir, "def456")
        updated = manager.update("mock-extension")

    assert updated is not None
    assert updated.requested_ref is None
    assert updated.resolved_ref == "def456"
